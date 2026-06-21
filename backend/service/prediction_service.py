import asyncio
import json
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from llm.base_client import BaseLLMClient, PredictionInput
from llm.deepseek_client import create_llm_client
from .rule_engine import RuleEngine, RulePrediction
from .calibration_service import CalibratedRuleEngine, load_calibrated_params
from .odds_fusion import fuse_multi_market_odds, fused_odds_to_dict
from .data_sources import meta_has_real_markets, is_real_sporttery
from .match_context import build_group_context, analyze_match_context
from data.worldcup_group_standings import load_group_standings
from db.models import Match, Team, Player, Odds, Prediction
from data.status_constants import MATCH_UPCOMING
from db.redis_client import cache_get, cache_set
from db.sqlite_write import IS_SQLITE, run_db_write
from utils.logger import logger
from utils.score_prediction import normalize_score_prediction, reconcile_prediction_view
from service.prediction_consistency import (
    encode_best_score,
    sync_reason_with_view,
    ensure_prediction_consistency,
    repair_stale_predictions,
)
from service.score_pick import (
    align_wdl_to_score_picks,
    reconcile_wdl_with_score_picks,
    dominant_wdl_outcome,
    run_full_score_pipeline,
    _score_outcome,
)
from service.confidence_service import compute_wdl_confidence


def get_configured_models() -> list[str]:
    """Return list of model names that have API keys configured."""
    import os
    models = []
    if os.getenv("DEEPSEEK_API_KEY", ""):
        models.append("deepseek")
    if os.getenv("QWEN_API_KEY", ""):
        models.append("qwen")
    if os.getenv("GLM_API_KEY", ""):
        models.append("glm")
    return models


def _validate_rates(win: float, draw: float, lose: float) -> tuple:
    """Ensure win+draw+lose ≈ 100, redistribute proportionally if not."""
    total = win + draw + lose
    if total <= 0:
        return (33.3, 33.4, 33.3)
    if abs(total - 100) < 0.5:
        return (round(win, 1), round(draw, 1), round(lose, 1))
    # Rescale to 100
    scale = 100.0 / total
    w = round(win * scale, 1)
    d = round(draw * scale, 1)
    l = round(100.0 - w - d, 1)  # ensure exact 100
    return (max(0.5, w), max(0.5, d), max(0.5, l))


def _append_calibrated_score_note(
    reason: str,
    best_scores: list[str] | None,
    upset: str | None,
    *,
    team_a: str = "",
    team_b: str = "",
    win_rate: float = 0,
    draw_rate: float = 0,
    lose_rate: float = 0,
) -> str:
    """Append synced W/D/L + score tail so narrative matches displayed badges."""
    if team_a and team_b:
        return sync_reason_with_view(
            reason,
            team_a,
            team_b,
            reconcile_prediction_view(best_scores, upset, win_rate, draw_rate, lose_rate),
        )
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    if not picks:
        return reason or ""
    note = f"[热门比分] {' / '.join(picks)}"
    if upset and upset != "?":
        note += f"（冷门 {upset}）"
    if note in (reason or ""):
        return reason or ""
    return f"{reason} | {note}" if reason else note


def _fuse_predictions(llm_results: list, rule_result, odds_dict: dict = None,
                      context_alerts: list = None, confidence_penalty: float = 0.0,
                      score_odds: dict | None = None,
                      group_context: dict | None = None,
                      team_a: dict | None = None,
                      team_b: dict | None = None,
                      stage: str | None = None) -> dict:
    """Fuse multiple LLM predictions with rule engine baseline and market odds.

    llm_results: list of PredictionOutput from successful LLM calls
    rule_result: RulePrediction from rule engine
    odds_dict: optional fused odds data for market-implied probability blending
    """
    n = len(llm_results)

    # Weighted average: prefer models with higher confidence
    confidences = [max(0.5, r.confidence) for r in llm_results]
    total_conf = sum(confidences)
    weights = [c / total_conf for c in confidences]

    win_rate = sum(r.win_rate * w for r, w in zip(llm_results, weights))
    draw_rate = sum(r.draw_rate * w for r, w in zip(llm_results, weights))
    lose_rate = sum(r.lose_rate * w for r, w in zip(llm_results, weights))

    # ── Market-implied probability anchor ──
    # If odds are available, compute the market-implied win/draw/lose percentages
    # and blend them with LLM predictions (20% weight for market signal)
    market_win = market_draw = market_lose = None
    if odds_dict:
        win_w = odds_dict.get("win_win")
        draw_o = odds_dict.get("draw")
        lose = odds_dict.get("win_lose")
        if win_w and draw_o and lose and win_w > 0 and draw_o > 0 and lose > 0:
            overround = 1 / win_w + 1 / draw_o + 1 / lose
            market_win = (1 / win_w) / overround * 100
            market_draw = (1 / draw_o) / overround * 100
            market_lose = (1 / lose) / overround * 100

            # Blend market-implied into LLM consensus (calibrated weight)
            MARKET_BLEND = load_calibrated_params().get("market_blend", 0.28)
            if (
                abs(win_rate - market_win) > 18
                and abs(lose_rate - market_lose) > 18
            ):
                MARKET_BLEND = min(0.48, MARKET_BLEND + 0.18)
            win_rate = (1 - MARKET_BLEND) * win_rate + MARKET_BLEND * market_win
            draw_rate = (1 - MARKET_BLEND) * draw_rate + MARKET_BLEND * market_draw
            lose_rate = (1 - MARKET_BLEND) * lose_rate + MARKET_BLEND * market_lose

            if abs(draw_rate - market_draw) > 15:
                correction = min(0.5, 0.25 + (abs(draw_rate - market_draw) - 15) / 60)
                old_draw = draw_rate
                draw_rate = (1 - correction) * draw_rate + correction * market_draw
                shift = draw_rate - old_draw
                win_rate -= shift / 2
                lose_rate -= shift / 2
                win_rate, draw_rate, lose_rate = _validate_rates(win_rate, draw_rate, lose_rate)

    # Rule engine safety net: if LLM consensus differs >25% from rule engine,
    # blend 25% rule engine weight
    if abs(win_rate - rule_result.win_rate) > 25:
        alpha = 0.75  # LLM weight
        win_rate = alpha * win_rate + 0.25 * rule_result.win_rate
        draw_rate = alpha * draw_rate + 0.25 * rule_result.draw_rate
        lose_rate = alpha * lose_rate + 0.25 * rule_result.lose_rate

    # Ensure rates sum to 100
    win_rate, draw_rate, lose_rate = _validate_rates(win_rate, draw_rate, lose_rate)

    # ── Aggregate top 3 scores across all models ──
    score_votes = {}
    for r, w in zip(llm_results, weights):
        for i, s in enumerate(r.best_scores):
            if s and s != "?":
                pos_weight = 1.0 - i * 0.15
                score_votes[s] = score_votes.get(s, 0) + w * pos_weight * 0.55

    for i, s in enumerate(rule_result.best_scores):
        if s and s != "?":
            score_votes[s] = score_votes.get(s, 0) + 0.65 * (1.0 - i * 0.15)

    if score_odds:
        from service.odds_fusion import score_distribution_from_odds
        crs_dist = score_distribution_from_odds(score_odds)
        crs_weight = load_calibrated_params().get("score_odds_blend", 0.35) + 0.15
        for s, p in crs_dist.items():
            score_votes[s] = score_votes.get(s, 0) + p * crs_weight * 2.0

    fav_out = dominant_wdl_outcome(win_rate, draw_rate, lose_rate)
    for r, w in zip(llm_results, weights):
        for i, s in enumerate(r.best_scores):
            if s and s != "?" and _score_outcome(s) == fav_out:
                score_votes[s] = score_votes.get(s, 0) + w * (0.42 - i * 0.08)

    model_hint = RuleEngine.pick_likely_scores(score_votes, max_count=3)
    pick_warnings: list[str] = []
    upset_score: str | None = None

    if score_odds:
        best_scores, upset_score, _, pick_warnings = run_full_score_pipeline(
            score_odds,
            win_rate=win_rate,
            draw_rate=draw_rate,
            lose_rate=lose_rate,
            expected_a=rule_result.expected_a,
            expected_b=rule_result.expected_b,
            model_scores=model_hint,
            stage=stage,
            sp_win=odds_dict.get("win_win") if odds_dict else None,
            sp_lose=odds_dict.get("win_lose") if odds_dict else None,
            sp_draw=odds_dict.get("draw") if odds_dict else None,
            handicap=(odds_dict or {}).get("handicap"),
            rank_a=(team_a or {}).get("rank"),
            rank_b=(team_b or {}).get("rank"),
            group_context=group_context,
            odds_dict=odds_dict,
            rule_result=rule_result,
            team_a=team_a,
            team_b=team_b,
        )
    else:
        best_scores = RuleEngine.pick_likely_scores(score_votes, max_count=2)
        upset_score = (
            rule_result.upset_score
            if rule_result.upset_score and rule_result.upset_score != "?"
            else None
        )

    if not best_scores:
        best_scores = (rule_result.best_scores or ["?"])[:2]

    # Majority vote for categorical predictions
    def weighted_vote(attr):
        votes = {}
        for r, w in zip(llm_results, weights):
            v = getattr(r, attr, "?")
            votes[v] = votes.get(v, 0) + w
        return max(votes, key=votes.get)

    handicap_result = weighted_vote("handicap_result")
    total_goals = weighted_vote("total_goals")

    if handicap_result == "?":
        handicap_result = rule_result.handicap_result
    if total_goals == "?":
        total_goals = rule_result.total_goals

    # Combine reasons (include situational alerts)
    reasons = []
    seen = set()
    for alert in (context_alerts or []):
        if alert and alert not in seen:
            seen.add(alert)
            reasons.append(f"[情境] {alert}")
    for r in llm_results:
        if r.reason and r.reason not in seen:
            seen.add(r.reason)
            prefix = r.model_used.split("-")[0] if r.model_used else "Model"
            reasons.append(f"[{prefix}] {r.reason}")
    reason = " | ".join(reasons)

    llm_conf = round(sum(r.confidence * w for r, w in zip(llm_results, weights)), 2)
    blend = {"win": win_rate, "draw": draw_rate, "lose": lose_rate}
    fav = max(blend, key=blend.get)
    fav_pct = blend[fav]

    market_fused = None
    if odds_dict and odds_dict.get("has_real_market"):
        market_fused = {
            "has_real_market": True,
            "imp_win": odds_dict.get("imp_win", market_win or 0),
            "imp_draw": odds_dict.get("imp_draw", market_draw or 0),
            "imp_lose": odds_dict.get("imp_lose", market_lose or 0),
        }
    elif market_win is not None:
        market_fused = {
            "has_real_market": True,
            "imp_win": market_win,
            "imp_draw": market_draw,
            "imp_lose": market_lose,
        }

    confidence = compute_wdl_confidence(
        pick_code=fav,
        blend_pct=fav_pct,
        confidence_penalty=confidence_penalty,
        alerts=context_alerts,
        ai_confidence=llm_conf,
        ai=blend,
        rule={
            "win": rule_result.win_rate,
            "draw": rule_result.draw_rate,
            "lose": rule_result.lose_rate,
        },
        market=market_fused,
        teams_available=bool(team_a and team_b),
        matchday=(group_context or {}).get("matchday", 0),
        blend=blend,
        pick_warnings=pick_warnings or None,
    )

    def short_name(full):
        if "deepseek" in full: return "DeepSeek"
        if "qwen" in full: return "Qwen"
        if "glm" in full or "GLM" in full: return "GLM"
        return full
    model_used = "+".join(short_name(r.model_used) for r in llm_results)

    normalized = normalize_score_prediction(best_scores, upset_score)
    win_rate, draw_rate, lose_rate = reconcile_wdl_with_score_picks(
        normalized["best_scores"], win_rate, draw_rate, lose_rate,
    )
    win_rate, draw_rate, lose_rate = align_wdl_to_score_picks(
        normalized["best_scores"], win_rate, draw_rate, lose_rate,
    )
    win_rate, draw_rate, lose_rate = _validate_rates(win_rate, draw_rate, lose_rate)
    if pick_warnings:
        reason = reason + " | [校验] " + "; ".join(pick_warnings[:2])
    reason = _append_calibrated_score_note(
        reason,
        normalized["best_scores"],
        normalized.get("upset_score"),
        team_a=(team_a or {}).get("name", ""),
        team_b=(team_b or {}).get("name", ""),
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
    )
    return {
        "win_rate": win_rate,
        "draw_rate": draw_rate,
        "lose_rate": lose_rate,
        **normalized,
        "handicap_result": handicap_result,
        "total_goals": total_goals,
        "reason": reason,
        "model_used": model_used,
        "confidence": confidence
    }


async def infer_matchday(match: Match, db: AsyncSession) -> int:
    """Infer group matchday (1-3) from earlier matches in the same group."""
    if match.stage != "小组赛" or not match.group_name:
        return 0
    count = (await db.execute(
        select(func.count(Match.id)).where(
            Match.group_name == match.group_name,
            Match.stage == "小组赛",
            Match.match_time < match.match_time,
        )
    )).scalar() or 0
    return min(3, count // 2 + 1)


def _implied_wdl(win_win: float, draw: float, win_lose: float) -> dict | None:
    if not all(v and v > 1.01 for v in (win_win, draw, win_lose)):
        return None
    inv = [1 / win_win, 1 / draw, 1 / win_lose]
    total = sum(inv)
    return {
        "imp_win": inv[0] / total * 100,
        "imp_draw": inv[1] / total * 100,
        "imp_lose": inv[2] / total * 100,
    }


def maybe_correct_odds_orientation(
    odds_dict: dict,
    rank_a: int | None,
    rank_b: int | None,
    *,
    rank_gap: int = 25,
    imp_margin: float = 12.0,
) -> dict:
    """Swap inverted W/D/L when FIFA rank gap strongly disagrees with market favourite."""
    if not odds_dict or rank_a is None or rank_b is None:
        return odds_dict
    win_win = odds_dict.get("win_win")
    draw = odds_dict.get("draw")
    win_lose = odds_dict.get("win_lose")
    imp = _implied_wdl(win_win, draw, win_lose)
    if not imp:
        return odds_dict

    ra, rb = int(rank_a), int(rank_b)
    invert = False
    if rb + rank_gap < ra and imp["imp_win"] - imp["imp_lose"] >= imp_margin:
        invert = True
    elif ra + rank_gap < rb and imp["imp_lose"] - imp["imp_win"] >= imp_margin:
        invert = True
    if not invert:
        return odds_dict

    from crawler.sporttery_client import _flip_handicap
    from data.match_status import _mirror_score_odds_value

    out = dict(odds_dict)
    out["win_win"], out["win_lose"] = win_lose, win_win
    if out.get("handicap_win") is not None and out.get("handicap_lose") is not None:
        out["handicap_win"], out["handicap_lose"] = out["handicap_lose"], out["handicap_win"]
    if out.get("handicap"):
        out["handicap"] = _flip_handicap(str(out["handicap"]))
    if out.get("score_odds"):
        mirrored = _mirror_score_odds_value(out["score_odds"])
        out["score_odds"] = json.loads(mirrored) if isinstance(mirrored, str) else mirrored
    if out.get("half_full_odds"):
        from data.match_status import _mirror_half_full_value
        mirrored_hf = _mirror_half_full_value(out["half_full_odds"])
        out["half_full_odds"] = json.loads(mirrored_hf) if isinstance(mirrored_hf, str) else mirrored_hf
    imp2 = _implied_wdl(out["win_win"], out["draw"], out["win_lose"])
    if imp2:
        out.update(imp2)
    logger.warning(
        "Corrected inverted market odds for rank %s vs %s (was imp %.0f/%.0f/%.0f)",
        ra, rb, imp["imp_win"], imp["imp_draw"], imp["imp_lose"],
    )
    return out


def prepare_fused_odds(odds: Odds = None, team_a: str = "", team_b: str = "") -> dict:
    """Build fused odds from DB — only real European/Asian markets in _meta."""
    empty = {
        "win_win": 0, "draw": 0, "win_lose": 0,
        "handicap": "0", "handicap_win": 0, "handicap_draw": 0, "handicap_lose": 0,
        "over_under": None, "over_odds": None, "under_odds": None,
        "score_odds": {}, "half_full_odds": {},
        "imp_win": 0, "imp_draw": 0, "imp_lose": 0,
        "market_signals": {"alerts": ["无真实外围盘口数据"]},
        "sources_used": [],
        "has_real_market": False,
    }
    if not odds:
        return empty

    raw_score = _parse_odds_json(odds.score_odds)
    meta = raw_score.pop("_meta", {}) if isinstance(raw_score, dict) else {}
    european = meta.get("european")
    macau = meta.get("macau")

    if not raw_score and odds.win_win and odds.draw and odds.win_lose:
        from crawler.odds_scraper import derive_score_odds
        raw_score = derive_score_odds(odds.win_win, odds.draw, odds.win_lose)

    if not meta_has_real_markets(meta):
        result = empty.copy()
        result["score_odds"] = raw_score
        result["half_full_odds"] = _parse_odds_json(odds.half_full_odds)
        if odds and odds.win_win:
            result.update({
                "win_win": odds.win_win,
                "draw": odds.draw,
                "win_lose": odds.win_lose,
                "handicap": odds.handicap,
                "handicap_win": odds.handicap_win,
                "handicap_draw": odds.handicap_draw,
                "handicap_lose": odds.handicap_lose,
                "over_under": odds.over_under if odds.over_under is not None else 2.5,
                "over_odds": odds.over_odds,
                "under_odds": odds.under_odds,
                "has_real_market": True,
                "sources_used": [odds.source or "stored_odds"],
                "market_signals": {"alerts": []},
            })
            implied = _implied_wdl(odds.win_win, odds.draw, odds.win_lose)
            if implied:
                result.update(implied)
        return result

    fused = fuse_multi_market_odds(european=european, macau=macau)
    result = fused_odds_to_dict(fused)
    result["score_odds"] = raw_score
    result["half_full_odds"] = _parse_odds_json(odds.half_full_odds)
    result["has_real_market"] = bool(result.get("sources_used"))
    return result


class PredictionService:

    def __init__(self):
        self.rule_engine = CalibratedRuleEngine()

    async def predict_match(self, match_id: int, db: AsyncSession,
                            model: str = None, skip_cache: bool = False) -> dict:
        """Predict match result.

        If model is None (default), auto-detects all configured LLM APIs
        and fuses their predictions. If model is specified, uses only that one.
        """
        # Check cache first (only for single-model or the default multi-model key)
        cache_suffix = model or "auto"
        cache_key = f"prediction:{match_id}:{cache_suffix}"
        if not skip_cache:
            cached = await cache_get(cache_key)
            if cached:
                view = reconcile_prediction_view(
                    cached.get("best_scores"),
                    cached.get("upset_score"),
                    cached.get("win_rate") or 50.0,
                    cached.get("draw_rate") or 28.0,
                    cached.get("lose_rate") or 50.0,
                )
                view["reason"] = sync_reason_with_view(
                    cached.get("reason"),
                    cached.get("team_a") or "",
                    cached.get("team_b") or "",
                    view,
                )
                return {**cached, **view}

        # 1. Collect match data
        match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
        if not match:
            return None

        team_a = (await db.execute(
            select(Team).where(Team.name == match.team_a, Team.competition_slug == match.competition_slug)
        )).scalar_one_or_none()
        team_b = (await db.execute(
            select(Team).where(Team.name == match.team_b, Team.competition_slug == match.competition_slug)
        )).scalar_one_or_none()

        team_a_dict = team_to_dict(team_a) if team_a else {"name": match.team_a}
        team_b_dict = team_to_dict(team_b) if team_b else {"name": match.team_b}

        odds = (await db.execute(select(Odds).where(Odds.match_id == match_id))).scalar_one_or_none()
        odds_dict = prepare_fused_odds(odds, match.team_a, match.team_b)
        odds_dict = maybe_correct_odds_orientation(
            odds_dict,
            (team_a_dict or {}).get("rank"),
            (team_b_dict or {}).get("rank"),
        )
        score_odds = odds_dict.get("score_odds", {})
        half_full_odds = odds_dict.get("half_full_odds", {})
        market_odds = odds_dict if odds_dict.get("has_real_market") else None

        players_a = await get_players(db, team_a.id) if team_a else []
        players_b = await get_players(db, team_b.id) if team_b else []

        # 2. Build group context + situational analysis
        matchday = await infer_matchday(match, db)
        standings = None
        if match.stage == "小组赛" and match.group_name:
            standings = await load_group_standings(
                db, match.competition_slug, match.group_name, match.match_time,
            )
        group_context = build_group_context(
            match.stage, match.group_name or "", matchday,
            match.team_a, match.team_b,
            team_a_dict.get("rank", 50), team_b_dict.get("rank", 50),
            location=match.location or "",
            standings=standings,
        )
        if match.stage == "小组赛" and match.group_name and matchday >= 2:
            from data.worldcup_group_standings import load_group_fifa_ranks
            from service.score_context import enrich_knockout_outlook
            from service.score_context import _R16_RUNNER_VS_WINNER, _R16_WINNER_VS_RUNNER

            letter = (match.group_name or "").strip().upper()
            paired: set[str] = set()
            if letter in _R16_WINNER_VS_RUNNER:
                paired.add(_R16_WINNER_VS_RUNNER[letter])
            if letter in _R16_RUNNER_VS_WINNER:
                paired.add(_R16_RUNNER_VS_WINNER[letter])
            paired_ranks: dict[str, list[int]] = {}
            for pg in paired:
                paired_ranks[pg] = await load_group_fifa_ranks(
                    db, match.competition_slug, pg,
                )
            enrich_knockout_outlook(
                group_context,
                match.team_a,
                match.team_b,
                int(team_a_dict.get("rank") or 50),
                int(team_b_dict.get("rank") or 50),
                paired_group_ranks=paired_ranks,
            )

        pre_result = self.rule_engine.evaluate(
            team_a_dict, team_b_dict, odds=None, group_context=group_context
        )
        context_analysis = analyze_match_context(
            team_a_dict, team_b_dict, group_context,
            odds_dict.get("market_signals", {}),
            {
                "win_pct": pre_result.win_rate,
                "market_win_pct": odds_dict.get("imp_win", 50),
                "market_draw_pct": odds_dict.get("imp_draw", 28),
            },
        )

        # 3. Calibrated rule engine with fused odds + context
        rule_result = self.rule_engine.evaluate(
            team_a_dict, team_b_dict, h2h=None, odds=market_odds,
            players_a=players_a, players_b=players_b,
            group_context=group_context,
            context_analysis=context_analysis,
            score_odds=score_odds,
        )

        # 3. Determine which models to call
        if model and model != "auto":
            if model == "rule_engine":
                models_to_call = []  # Skip all LLMs, use rule engine only
            else:
                models_to_call = [model]
        else:
            models_to_call = get_configured_models()

        # 4. Call LLMs in parallel
        llm_results = []
        if models_to_call:
            llm_input = PredictionInput(
                match_id=match_id,
                team_a=team_a_dict,
                team_b=team_b_dict,
                players_a=players_a,
                players_b=players_b,
                odds=market_odds or {},
                score_odds=score_odds,
                half_full_odds=half_full_odds,
                group_context=group_context,
            )

            async def call_one(m: str):
                client = create_llm_client(m)
                return await client.predict(llm_input)

            results = await asyncio.gather(*[call_one(m) for m in models_to_call], return_exceptions=True)
            llm_results = [r for r in results if r is not None and not isinstance(r, Exception)]

        # 5. Fuse results with market-implied probability blending
        context_alerts = context_analysis.alerts
        conf_penalty = context_analysis.confidence_penalty
        if llm_results:
            fused = _fuse_predictions(
                llm_results, rule_result, odds_dict,
                context_alerts=context_alerts, confidence_penalty=conf_penalty,
                score_odds=score_odds,
                group_context=group_context,
                team_a=team_a_dict,
                team_b=team_b_dict,
                stage=match.stage,
            )
        else:
            reason_parts = ["基于历史回测校准模型：欧赔+澳盘融合、六维实力、战术匹配"]
            reason_parts.extend(f"⚠ {a}" for a in context_alerts[:3])
            pick_warnings: list[str] = []
            if score_odds:
                scores, upset, _, pick_warnings = run_full_score_pipeline(
                    score_odds,
                    win_rate=rule_result.win_rate,
                    draw_rate=rule_result.draw_rate,
                    lose_rate=rule_result.lose_rate,
                    expected_a=rule_result.expected_a,
                    expected_b=rule_result.expected_b,
                    model_scores=rule_result.best_scores,
                    stage=match.stage,
                    sp_win=market_odds.get("win_win") if market_odds else None,
                    sp_lose=market_odds.get("win_lose") if market_odds else None,
                    sp_draw=market_odds.get("draw") if market_odds else None,
                    handicap=(market_odds or {}).get("handicap"),
                    rank_a=(team_a_dict or {}).get("rank"),
                    rank_b=(team_b_dict or {}).get("rank"),
                    group_context=group_context,
                    odds_dict=market_odds,
                    rule_result=rule_result,
                    team_a=team_a_dict,
                    team_b=team_b_dict,
                )
            else:
                scores = rule_result.best_scores
                upset = rule_result.upset_score if rule_result.upset_score != "?" else None
            rule_norm = normalize_score_prediction(scores, upset)
            w, d, l = reconcile_wdl_with_score_picks(
                rule_norm["best_scores"],
                rule_result.win_rate,
                rule_result.draw_rate,
                rule_result.lose_rate,
            )
            w, d, l = align_wdl_to_score_picks(
                rule_norm["best_scores"], w, d, l,
            )
            w, d, l = _validate_rates(w, d, l)
            if pick_warnings:
                reason_parts.append("[校验] " + "; ".join(pick_warnings[:2]))
            reason_text = _append_calibrated_score_note(
                " | ".join(reason_parts),
                rule_norm["best_scores"],
                rule_norm.get("upset_score"),
                team_a=team_a_dict.get("name", match.team_a),
                team_b=team_b_dict.get("name", match.team_b),
                win_rate=w,
                draw_rate=d,
                lose_rate=l,
            )
            blend = {"win": w, "draw": d, "lose": l}
            fav = max(blend, key=blend.get)
            market_fused = None
            if market_odds and market_odds.get("has_real_market"):
                market_fused = {
                    "has_real_market": True,
                    "imp_win": market_odds.get("imp_win", 0),
                    "imp_draw": market_odds.get("imp_draw", 0),
                    "imp_lose": market_odds.get("imp_lose", 0),
                }
            fused = {
                "win_rate": w,
                "draw_rate": d,
                "lose_rate": l,
                **rule_norm,
                "handicap_result": rule_result.handicap_result,
                "total_goals": rule_result.total_goals,
                "reason": reason_text,
                "model_used": "rule_engine_calibrated",
                "confidence": compute_wdl_confidence(
                    pick_code=fav,
                    blend_pct=blend[fav],
                    confidence_penalty=conf_penalty,
                    alerts=context_alerts,
                    rule=blend,
                    market=market_fused,
                    teams_available=bool(team_a_dict and team_b_dict),
                    matchday=group_context.get("matchday", 0),
                    blend=blend,
                    pick_warnings=pick_warnings or None,
                ),
            }

        result = {
            "match_id": match_id,
            "team_a": match.team_a,
            "team_b": match.team_b,
            "stage": match.stage,
            "market_signals": odds_dict.get("market_signals", {}),
            "context_alerts": context_alerts,
            "odds_sources": odds_dict.get("sources_used", []),
            **fused
        }

        # 6. Save to DB (replace any existing prediction for this match)
        try:
            from sqlalchemy import delete

            async def _persist_prediction():
                await db.execute(delete(Prediction).where(Prediction.match_id == match_id))
                db.add(Prediction(
                    match_id=match_id,
                    win_rate=result["win_rate"],
                    draw_rate=result["draw_rate"],
                    lose_rate=result["lose_rate"],
                    best_score=encode_best_score(
                        result["best_scores"], result.get("upset_score")
                    ),
                    handicap_result=result["handicap_result"],
                    total_goals=result["total_goals"],
                    reason=result["reason"],
                    model_used=result["model_used"],
                    confidence=result["confidence"],
                ))

            await run_db_write(db, _persist_prediction)
        except Exception as e:
            logger.error(f"Failed to save prediction for match {match_id}: {e}")
            await db.rollback()

        # Cache for 1 hour
        await cache_set(cache_key, result, ttl=3600)

        return result

    async def batch_predict(
        self,
        db: AsyncSession,
        model: str = None,
        *,
        competition_slug: str | None = None,
        on_progress=None,
    ):
        """Predict upcoming matches using auto-detected or specified models.

        Processes matches in parallel batches using independent DB sessions.
        """
        from db import async_session as session_factory

        query = select(Match).where(Match.status == MATCH_UPCOMING)
        if competition_slug:
            query = query.where(Match.competition_slug == competition_slug)
        matches = (await db.execute(query.order_by(Match.match_time))).scalars().all()

        if not matches:
            return []

        total = len(matches)
        # SQLite: serial per match; DB writes use run_db_write — do not hold write_lock
        # across LLM calls (would block on startup/crawler and freeze progress at 0/N).
        if IS_SQLITE:
            results: list = []
            failed_ids: list[int] = []

            await _report_progress(on_progress, 0, 0, 0)
            for idx, match in enumerate(matches, start=1):
                await _report_progress(
                    on_progress, idx - 1, len(results), len(failed_ids), match=match,
                )
                try:
                    result = await self.predict_match(match.id, db, model)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Batch predict failed for match {match.id}: {e}")
                    failed_ids.append(match.id)
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                await _report_progress(
                    on_progress, idx, len(results), len(failed_ids), match=match,
                )
            if failed_ids:
                logger.warning(
                    f"Batch predict: {len(failed_ids)}/{total} matches failed: {failed_ids}"
                )
            logger.info(f"Batch predicted {len(results)}/{total} matches (sqlite serial)")
            return results

        # LLM calls dominate runtime; DB writes are brief via run_db_write.
        concurrency = 4 if model == "rule_engine" else 8
        semaphore = asyncio.Semaphore(concurrency)
        failed_ids: list[int] = []
        done = 0
        success_count = 0
        progress_lock = asyncio.Lock()

        async def _tick_progress() -> None:
            if on_progress:
                await _maybe_await(on_progress(done, success_count, len(failed_ids)))

        async def predict_one(match):
            nonlocal done, success_count
            async with semaphore:
                async with session_factory() as session:
                    try:
                        result = await self.predict_match(match.id, session, model)
                        async with progress_lock:
                            done += 1
                            if result:
                                success_count += 1
                            await _tick_progress()
                        return result
                    except Exception as e:
                        logger.error(f"Batch predict failed for match {match.id}: {e}")
                        failed_ids.append(match.id)
                        try:
                            await session.rollback()
                        except Exception:
                            pass
                        async with progress_lock:
                            done += 1
                            await _tick_progress()
                        return None

        logger.info(
            f"Batch predict start: {total} matches, model={model or 'auto'}, "
            f"competition={competition_slug or 'all'}, concurrency={concurrency}"
        )
        await _report_progress(on_progress, 0, 0, 0)
        results_raw = await asyncio.gather(*[predict_one(m) for m in matches])
        results = [r for r in results_raw if r is not None]

        if failed_ids:
            logger.warning(f"Batch predict: {len(failed_ids)}/{total} matches failed: {failed_ids}")

        logger.info(f"Batch predicted {len(results)}/{total} matches")
        return results


def team_to_dict(team: Team) -> dict:
    return {
        "name": team.name,
        "rank": team.rank,
        "attack": team.attack,
        "defend": team.defend,
        "midfield": team.midfield,
        "speed": team.speed,
        "physical": team.physical,
        "tactic": team.tactic,
        "price": team.price,
        "group_name": team.group_name
    }


def odds_to_dict(odds: Odds) -> dict:
    result = {
        "win_win": odds.win_win,
        "draw": odds.draw,
        "win_lose": odds.win_lose,
        "handicap": odds.handicap,
        "handicap_win": odds.handicap_win,
        "handicap_draw": odds.handicap_draw,
        "handicap_lose": odds.handicap_lose,
        "over_under": odds.over_under,
        "over_odds": odds.over_odds,
        "under_odds": odds.under_odds
    }
    return result


async def _maybe_await(result) -> None:
    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
        await result


async def _report_progress(on_progress, done: int, success: int, failed: int, *, match=None) -> None:
    if not on_progress:
        return
    extra = {}
    if match is not None:
        extra["current_match"] = f"{match.team_a} vs {match.team_b}"
    await _maybe_await(on_progress(done, success, failed, **extra))


def _encode_best_score(scores: list, upset: str | None = None) -> str:
    """Backward-compatible alias."""
    return encode_best_score(scores, upset)


def _parse_odds_json(val):
    """Parse JSON odds field safely."""
    if val is None:
        return {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


async def get_players(db: AsyncSession, team_id: int) -> list[dict]:
    players = (await db.execute(
        select(Player).where(Player.team_id == team_id).order_by(Player.ability.desc()).limit(11)
    )).scalars().all()
    return [
        {
            "name": p.name,
            "position": p.position,
            "status": p.status,
            "ability": p.ability,
            "is_starter": p.is_starter
        }
        for p in players
    ]
