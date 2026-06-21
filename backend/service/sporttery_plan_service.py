"""
China Sports Lottery purchase plan — today's World Cup singles & parlay suggestions.

Integrates: sporttery.cn on-sale odds, crawler-fused European/Asian markets,
team/player crawler data, rule engine, and AI predictions.
For reference only; not betting advice.
"""
from __future__ import annotations

import json
from datetime import datetime, date as date_type
from math import prod
from statistics import mean
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.sporttery_client import (
    fetch_sporttery_on_sale,
    find_sporttery_match,
    get_sporttery_fetch_status,
    normalize_team_name,
    to_db_odds,
)
from utils.datetime_helpers import china_today
from db.models import Match, Odds, Prediction, Team
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, PLAYER_ACTIVE, match_status_in_db_values
from service.calibration_service import CalibratedRuleEngine
from service.confidence_service import compute_score_confidence, compute_wdl_confidence
from service.match_context import analyze_match_context, build_group_context, apply_context_to_rates
from data.worldcup_group_standings import load_group_standings
from service.prediction_service import (
    get_players,
    infer_matchday,
    prepare_fused_odds,
    maybe_correct_odds_orientation,
    team_to_dict,
)

from data.competitions import get_competition, league_hints_for

WORLD_CUP_LEAGUE_HINTS = ("世界", "世界杯", "World Cup", "FIFA")

# 参考单注金额（元），体彩比分单关/过关常用 2 元起步
DEFAULT_STAKE_YUAN = 2.0


def _bet_payout(odds: float, stake: float = DEFAULT_STAKE_YUAN) -> dict:
    """Nominal return = stake × CRS odds; profit = return − stake."""
    if not odds or odds <= 0:
        return {"stake_yuan": stake, "return_yuan": 0.0, "profit_yuan": 0.0}
    ret = round(float(odds) * stake, 2)
    return {
        "stake_yuan": stake,
        "return_yuan": ret,
        "profit_yuan": round(ret - stake, 2),
    }

_rule_engine = CalibratedRuleEngine()

# Blend weights when all sources available (renormalized if some missing)
_BLEND_WEIGHTS = {
    "ai": 0.35,
    "rule": 0.30,
    "market": 0.20,
    "sporttery": 0.15,
}


def _is_competition_league(league: str, hints: tuple[str, ...]) -> bool:
    if not league:
        return False
    return any(h in league for h in hints)


def _is_purchasable_today(st_match: dict, today: date_type) -> bool:
    """True when sporttery lists the match for today's sale window (China date)."""
    sell_status = str(st_match.get("sell_status") or "").strip()
    if sell_status and sell_status not in ("1", "Selling", "selling", "在售"):
        lowered = sell_status.lower()
        if lowered in ("0", "stop", "stopped", "停售", "close", "closed"):
            return False

    kickoff = st_match.get("kickoff")
    if kickoff and kickoff.date() < today:
        return False

    sale_date = st_match.get("sale_date")
    if sale_date:
        try:
            return date_type.fromisoformat(str(sale_date)[:10]) == today
        except ValueError:
            pass

    # On-sale pool item without sale_date: still purchasable if not kicked off
    return True


def _implied_probs(win: float, draw: float, lose: float) -> dict[str, float]:
    if not all(v and v > 0 for v in (win, draw, lose)):
        return {}
    inv = {"win": 1 / win, "draw": 1 / draw, "lose": 1 / lose}
    total = sum(inv.values())
    return {k: v / total * 100 for k, v in inv.items()}


def _pick_label(code: str) -> str:
    return {"win": "胜", "draw": "平", "lose": "负"}.get(code, code)


def _play_type_label(use_handicap: bool) -> str:
    return "让球胜平负" if use_handicap else "胜平负"


def _parse_best_score_payload(val) -> dict:
    """Parse prediction.best_score — array, object, or legacy string."""
    if val is None:
        return {"scores": [], "upset": None}
    if isinstance(val, dict):
        scores = val.get("scores") or []
        upset = val.get("upset")
        return {"scores": scores, "upset": upset}
    if isinstance(val, list):
        return {"scores": val, "upset": None}
    if isinstance(val, str):
        if val.startswith("{") or val.startswith("["):
            try:
                return _parse_best_score_payload(json.loads(val))
            except json.JSONDecodeError:
                pass
        return {"scores": [val] if val and val != "?" else [], "upset": None}
    return {"scores": [str(val)] if val else [], "upset": None}


def _collect_likely_scores(analysis: dict, *, exclude_upset: Optional[str] = None) -> list[str]:
    """Top likely scorelines for purchase plan — excludes upset/cold picks."""
    ordered: list[str] = []
    prediction = analysis.get("prediction")
    rule_result = analysis.get("rule_result")
    skip = {exclude_upset} if exclude_upset and exclude_upset != "?" else set()

    if prediction and prediction.best_score:
        payload = _parse_best_score_payload(prediction.best_score)
        u = payload.get("upset")
        if u and u != "?":
            skip.add(u)
        for s in payload.get("scores") or []:
            if s and s != "?" and s not in ordered and s not in skip:
                ordered.append(s)
        return ordered[:5]

    if rule_result and getattr(rule_result, "best_scores", None):
        u = getattr(rule_result, "upset_score", None)
        if u and u != "?":
            skip.add(u)
        for s in rule_result.best_scores:
            if s and s != "?" and s not in ordered and s not in skip:
                ordered.append(s)

    return ordered[:5]


def _get_upset_score(analysis: dict) -> Optional[str]:
    """Cold/upset scoreline — reference only, never the primary purchase pick."""
    prediction = analysis.get("prediction")
    if prediction and prediction.best_score:
        upset = _parse_best_score_payload(prediction.best_score).get("upset")
        if upset and upset != "?":
            return upset

    rule_result = analysis.get("rule_result")
    if rule_result:
        upset = getattr(rule_result, "upset_score", None)
        if upset and upset != "?":
            return upset
    return None


def _pick_likely_with_odds(
    likely_scores: list[str],
    crs_odds: dict[str, float],
    *,
    count: int = 2,
    exclude: Optional[set[str]] = None,
) -> list[tuple[str, float, int]]:
    """Top-N model scorelines that have CRS odds, preserving model rank order."""
    skip = exclude or set()
    picks: list[tuple[str, float, int]] = []
    for rank, scoreline in enumerate(likely_scores):
        if scoreline in skip:
            continue
        odd = crs_odds.get(scoreline)
        if not odd:
            continue
        picks.append((scoreline, odd, rank))
        if len(picks) >= count:
            break
    return picks


def _supplement_likely_scores(
    needed: int,
    used: set[str],
    crs_odds: dict[str, float],
    blend: dict[str, float],
    *,
    exclude: Optional[set[str]] = None,
) -> list[tuple[str, float, int]]:
    """Fill missing likely picks from on-sale CRS when model returns <2 lines."""
    if needed <= 0:
        return []
    skip = used | (exclude or set())
    fav = max(blend, key=blend.get)
    ranked: list[tuple[float, str, float]] = []
    for scoreline, odd in crs_odds.items():
        if scoreline in skip:
            continue
        outcome = _outcome_from_score(scoreline)
        if outcome != fav:
            continue
        implied = (1 / odd) if odd > 0 else 0
        align = blend.get(outcome, 33.0) / 100
        score = align * 0.65 + implied * 0.35 + 0.06
        ranked.append((score, scoreline, odd))
    ranked.sort(key=lambda x: -x[0])
    return [(s, o, 8) for _, s, o in ranked[:needed]]


def _resolve_upset_pick(
    upset_score: Optional[str],
    used_scores: set[str],
    crs_odds: dict[str, float],
    blend: dict[str, float],
    analysis: dict,
) -> Optional[tuple[str, float]]:
    """One cold scoreline with CRS odds; prefers model upset, else best CRS upset candidate."""
    if upset_score and upset_score not in used_scores:
        odd = crs_odds.get(upset_score)
        if odd:
            return upset_score, odd

    fav = max(blend, key=blend.get)
    candidates: list[tuple[float, str, float]] = []
    for scoreline, odd in crs_odds.items():
        if scoreline in used_scores:
            continue
        outcome = _outcome_from_score(scoreline)
        if outcome == fav:
            continue
        if odd < 5.5 or odd > 50:
            continue
        value = _score_pick_value(scoreline, 6, odd, blend, analysis, is_upset=True)
        candidates.append((value, scoreline, odd))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    _, scoreline, odd = candidates[0]
    return scoreline, odd


def _build_score_picks(
    likely_scores: list[str],
    upset_score: Optional[str],
    crs_odds: dict[str, float],
    blend: dict[str, float],
    analysis: dict,
    *,
    sporttery_crs: Optional[dict[str, float]] = None,
) -> list[dict]:
    """Two likely + one upset aligned with canonical scores (same as schedule API)."""
    from utils.score_prediction import normalize_score_prediction

    norm = normalize_score_prediction(likely_scores, upset_score)
    canonical_likely = norm["best_scores"]
    canonical_upset = norm["upset_score"]
    st_crs = sporttery_crs or crs_odds

    if not canonical_likely:
        return []

    score_picks: list[dict] = []
    used: set[str] = set()
    for i, scoreline in enumerate(canonical_likely[:2]):
        odd = st_crs.get(scoreline) or crs_odds.get(scoreline) or 0.0
        score_picks.append({
            "score": scoreline,
            "odds": odd,
            "type": "likely",
            "rank": i + 1,
            "is_upset": False,
            "has_sporttery_odd": bool(st_crs.get(scoreline)),
        })
        used.add(scoreline)

    if canonical_upset and canonical_upset not in used:
        uo = st_crs.get(canonical_upset) or crs_odds.get(canonical_upset) or 0.0
        score_picks.append({
            "score": canonical_upset,
            "odds": uo,
            "type": "upset",
            "rank": 1,
            "is_upset": True,
            "has_sporttery_odd": bool(st_crs.get(canonical_upset)),
        })
    return score_picks


def _clean_crs_odds(score_odds: dict) -> dict[str, float]:
    if not score_odds:
        return {}
    from crawler.sporttery_client import normalize_score_line

    cleaned: dict[str, float] = {}
    for k, v in score_odds.items():
        if str(k).startswith("_") or not v:
            continue
        try:
            odd = float(v)
        except (TypeError, ValueError):
            continue
        if odd <= 1.01:
            continue
        key = normalize_score_line(k) if ":" in str(k) or "：" in str(k) else str(k)
        cleaned[key] = odd
    return cleaned


def _outcome_from_score(score: str) -> str:
    """Map scoreline (team_a:team_b) to win/draw/lose."""
    try:
        ga, gb = map(int, score.split(":"))
    except (ValueError, AttributeError):
        return "draw"
    if ga > gb:
        return "win"
    if ga < gb:
        return "lose"
    return "draw"


def _team_strength_summary(team: Optional[dict], players: list[dict]) -> dict:
    if not team:
        return {"available": False}
    starters = [p for p in players if p.get("is_starter")]
    injured = [p["name"] for p in players if p.get("status") and p["status"] != PLAYER_ACTIVE]
    abilities = [p["ability"] for p in starters if p.get("ability")]
    return {
        "available": True,
        "name": team.get("name"),
        "rank": team.get("rank"),
        "attack": team.get("attack"),
        "defend": team.get("defend"),
        "midfield": team.get("midfield"),
        "speed": team.get("speed"),
        "physical": team.get("physical"),
        "tactic": team.get("tactic"),
        "price": team.get("price"),
        "group_name": team.get("group_name"),
        "avg_starter_ability": round(mean(abilities), 1) if abilities else None,
        "injuries": injured[:5],
        "starter_count": len(starters),
    }


def _blend_probs(sources: dict[str, dict[str, float]]) -> dict[str, float]:
    """Weighted blend of win/draw/lose percentages; renormalize missing sources."""
    active = {k: w for k, w in _BLEND_WEIGHTS.items() if k in sources}
    if not active:
        return {"win": 33.3, "draw": 33.3, "lose": 33.4}
    total_w = sum(active.values())
    out = {"win": 0.0, "draw": 0.0, "lose": 0.0}
    for key, weight in active.items():
        norm = weight / total_w
        rates = sources[key]
        for code in ("win", "draw", "lose"):
            out[code] += rates.get(code, 33.0) * norm
    s = sum(out.values())
    if s > 0:
        out = {k: v / s * 100 for k, v in out.items()}
    return {k: round(v, 1) for k, v in out.items()}


async def _latest_predictions(db: AsyncSession, match_ids: list[int]) -> dict[int, Prediction]:
    if not match_ids:
        return {}
    rows = (await db.execute(
        select(Prediction)
        .where(Prediction.match_id.in_(match_ids))
        .order_by(Prediction.match_id, Prediction.create_time.desc())
    )).scalars().all()
    out: dict[int, Prediction] = {}
    for p in rows:
        if p.match_id not in out:
            out[p.match_id] = p
    return out


async def _find_db_match(
    db: AsyncSession,
    home: str,
    away: str,
    kickoff: Optional[datetime],
    competition_slug: str = "worldcup-2026",
) -> Optional[Match]:
    home_n = normalize_team_name(home)
    away_n = normalize_team_name(away)
    matches = (await db.execute(
        select(Match).where(
            Match.competition_slug == competition_slug,
            Match.status.in_(match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)),
        )
    )).scalars().all()
    candidates = []
    for m in matches:
        a, b = normalize_team_name(m.team_a), normalize_team_name(m.team_b)
        if not ((a == home_n and b == away_n) or (a == away_n and b == home_n)):
            continue
        score = 0
        if kickoff and m.match_time:
            delta_h = abs((m.match_time - kickoff).total_seconds()) / 3600
            if delta_h <= 3:
                score += 10
            elif delta_h <= 24:
                score += 5
        candidates.append((score, m))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


async def _build_match_analysis(
    db: AsyncSession,
    db_match: Optional[Match],
    prediction: Optional[Prediction],
    sporttery_odds: dict,
) -> dict:
    """Collect team, odds, rule engine, AI and context signals for one match."""
    if not db_match:
        return {
            "has_db_match": False,
            "blend": {"win": 33.3, "draw": 33.3, "lose": 33.4},
            "references": {"data_sources": ["sporttery.cn"]},
            "confidence_penalty": 0.15,
            "alerts": [],
        }

    team_a_obj = (await db.execute(
        select(Team).where(Team.name == db_match.team_a, Team.competition_slug == db_match.competition_slug)
    )).scalar_one_or_none()
    team_b_obj = (await db.execute(
        select(Team).where(Team.name == db_match.team_b, Team.competition_slug == db_match.competition_slug)
    )).scalar_one_or_none()
    team_a_dict = team_to_dict(team_a_obj) if team_a_obj else {"name": db_match.team_a}
    team_b_dict = team_to_dict(team_b_obj) if team_b_obj else {"name": db_match.team_b}

    players_a = await get_players(db, team_a_obj.id) if team_a_obj else []
    players_b = await get_players(db, team_b_obj.id) if team_b_obj else []

    odds_row = (await db.execute(
        select(Odds).where(Odds.match_id == db_match.id).order_by(Odds.id.desc())
    )).scalars().first()
    fused = prepare_fused_odds(odds_row, db_match.team_a, db_match.team_b)
    fused = maybe_correct_odds_orientation(
        fused, team_a_dict.get("rank"), team_b_dict.get("rank"),
    )

    matchday = await infer_matchday(db_match, db)
    standings = None
    if db_match.stage == "小组赛" and db_match.group_name:
        standings = await load_group_standings(
            db, db_match.competition_slug, db_match.group_name, db_match.match_time,
        )
    group_context = build_group_context(
        db_match.stage, db_match.group_name or "", matchday,
        db_match.team_a, db_match.team_b,
        team_a_dict.get("rank", 50), team_b_dict.get("rank", 50),
        location=db_match.location or "",
        standings=standings,
    )

    pre_rule = _rule_engine.evaluate(
        team_a_dict, team_b_dict, odds=None, group_context=group_context,
    )
    context_analysis = analyze_match_context(
        team_a_dict, team_b_dict, group_context,
        fused.get("market_signals", {}),
        {
            "win_pct": pre_rule.win_rate,
            "market_win_pct": fused.get("imp_win", 50),
            "market_draw_pct": fused.get("imp_draw", 28),
        },
    )

    rule_result = _rule_engine.evaluate(
        team_a_dict, team_b_dict, h2h=None,
        odds=fused if fused.get("has_real_market") else None,
        players_a=players_a, players_b=players_b,
        group_context=group_context,
        context_analysis=context_analysis,
        score_odds=fused.get("score_odds", {}),
    )
    rule_win, rule_draw, rule_lose = apply_context_to_rates(
        rule_result.win_rate, rule_result.draw_rate, rule_result.lose_rate,
        context_analysis,
    )

    blend_sources: dict[str, dict[str, float]] = {}
    data_sources = ["sporttery.cn"]

    st_imp = _implied_probs(
        sporttery_odds.get("win_win", 0),
        sporttery_odds.get("draw", 0),
        sporttery_odds.get("win_lose", 0),
    )
    if st_imp:
        blend_sources["sporttery"] = st_imp

    if fused.get("has_real_market"):
        blend_sources["market"] = {
            "win": fused.get("imp_win", 33),
            "draw": fused.get("imp_draw", 33),
            "lose": fused.get("imp_lose", 34),
        }
        data_sources.extend(fused.get("sources_used") or ["外围盘口"])

    blend_sources["rule"] = {"win": rule_win, "draw": rule_draw, "lose": rule_lose}
    data_sources.append("球队爬虫+规则引擎")

    if prediction:
        from utils.score_prediction import parse_best_score_payload, reconcile_prediction_view
        payload = parse_best_score_payload(prediction.best_score)
        dr = prediction.draw_rate if prediction.draw_rate is not None else max(
            0.0, 100.0 - (prediction.win_rate or 0) - (prediction.lose_rate or 0),
        )
        ai_view = reconcile_prediction_view(
            payload.get("scores"),
            payload.get("upset"),
            prediction.win_rate or 50.0,
            dr,
            prediction.lose_rate or 50.0,
        )
        blend_sources["ai"] = {
            "win": ai_view["win_rate"],
            "draw": ai_view["draw_rate"],
            "lose": ai_view["lose_rate"],
        }
        data_sources.append(f"AI预测({prediction.model_used or 'fusion'})")
    elif team_a_obj and team_b_obj:
        data_sources.append("球队能力数据")

    blend = _blend_probs(blend_sources)

    team_a_ref = _team_strength_summary(team_a_dict, players_a)
    team_b_ref = _team_strength_summary(team_b_dict, players_b)

    references = {
        "data_sources": list(dict.fromkeys(data_sources)),
        "teams": {"team_a": team_a_ref, "team_b": team_b_ref},
        "match_context": {
            "stage": db_match.stage,
            "group": db_match.group_name,
            "matchday": matchday,
            "location": db_match.location,
        },
        "odds": {
            "sporttery": {
                "win": sporttery_odds.get("win_win"),
                "draw": sporttery_odds.get("draw"),
                "lose": sporttery_odds.get("win_lose"),
                "handicap": sporttery_odds.get("handicap"),
                "source": "sporttery.cn",
            },
            "market_fused": {
                "imp_win": fused.get("imp_win"),
                "imp_draw": fused.get("imp_draw"),
                "imp_lose": fused.get("imp_lose"),
                "sources": fused.get("sources_used", []),
                "has_real_market": fused.get("has_real_market", False),
                "handicap": fused.get("handicap"),
                "over_under": fused.get("over_under"),
            },
            "db_source": odds_row.source if odds_row else None,
            "db_update_time": odds_row.update_time.isoformat() if odds_row and odds_row.update_time else None,
        },
        "models": {
            "ai": {
                "win": prediction.win_rate,
                "draw": prediction.draw_rate,
                "lose": prediction.lose_rate,
                "model": prediction.model_used,
                "confidence": prediction.confidence,
                "reason_snippet": (prediction.reason or "")[:120],
            } if prediction else None,
            "rule_engine": {
                "win": rule_win,
                "draw": rule_draw,
                "lose": rule_lose,
            },
        },
        "fused_recommendation": blend,
        "alerts": context_analysis.alerts + fused.get("market_signals", {}).get("alerts", [])[:3],
    }

    return {
        "has_db_match": True,
        "blend": blend,
        "references": references,
        "confidence_penalty": context_analysis.confidence_penalty,
        "alerts": references["alerts"],
        "matchday": matchday,
        "rule_result": rule_result,
        "prediction": prediction,
        "db_fused": fused,
        "db_spf": {
            "win_win": odds_row.win_win if odds_row else None,
            "draw": odds_row.draw if odds_row else None,
            "win_lose": odds_row.win_lose if odds_row else None,
            "handicap": odds_row.handicap if odds_row else None,
        },
        "teams": {"team_a": team_a_dict, "team_b": team_b_dict},
    }


def _build_reason(
    code: str,
    odds: float,
    blend_pct: float,
    analysis: dict,
) -> str:
    parts = []
    implied = (1 / odds * 100) if odds > 0 else 0
    edge = blend_pct - implied

    refs = analysis.get("references", {})
    teams = refs.get("teams", {})
    ta = teams.get("team_a", {})
    tb = teams.get("team_b", {})

    if ta.get("available") and tb.get("available"):
        rank_a, rank_b = ta.get("rank"), tb.get("rank")
        if rank_a and rank_b:
            parts.append(f"FIFA排名{rank_a} vs {rank_b}")
        atk_gap = (ta.get("attack") or 0) - (tb.get("attack") or 0)
        if abs(atk_gap) >= 8:
            fav = ta["name"] if atk_gap > 0 else tb["name"]
            parts.append(f"进攻差{abs(atk_gap)}分倾向{fav}")

    ai = refs.get("models", {}).get("ai")
    if ai:
        parts.append(f"AI融合{ai.get('model', 'auto')}{_pick_label(code)}{ai.get(code, 0):.0f}%")
    else:
        rule = refs.get("models", {}).get("rule_engine", {})
        if rule:
            parts.append(f"规则引擎{_pick_label(code)}{rule.get(code, 0):.0f}%")

    market = refs.get("odds", {}).get("market_fused", {})
    if market.get("has_real_market"):
        imp_key = {"win": "imp_win", "draw": "imp_draw", "lose": "imp_lose"}[code]
        parts.append(f"外围盘口隐含{market.get(imp_key, 0):.0f}%")

    if edge > 5:
        parts.append(f"综合胜率{blend_pct:.0f}%高于体彩隐含{implied:.0f}%，存在价值")
    elif blend_pct >= 45:
        parts.append(f"多源融合倾向{_pick_label(code)}（{blend_pct:.0f}%）")
    else:
        parts.append(f"体彩{odds:.2f}，综合参考{_pick_label(code)} {blend_pct:.0f}%")

    alerts = analysis.get("alerts") or []
    if alerts:
        parts.append(alerts[0])

    return "；".join(parts[:4])


def _calc_confidence(analysis: dict, pick_code: str, blend_pct: float) -> float:
    refs = analysis.get("references", {})
    teams = refs.get("teams", {})
    ai = refs.get("models", {}).get("ai")
    return compute_wdl_confidence(
        pick_code=pick_code,
        blend_pct=blend_pct,
        confidence_penalty=analysis.get("confidence_penalty", 0),
        alerts=analysis.get("alerts"),
        ai_confidence=float(ai["confidence"]) if ai and ai.get("confidence") else None,
        ai=ai,
        rule=refs.get("models", {}).get("rule_engine"),
        market=refs.get("odds", {}).get("market_fused"),
        teams_available=bool(
            teams.get("team_a", {}).get("available") and teams.get("team_b", {}).get("available")
        ),
        matchday=analysis.get("matchday") or refs.get("match_context", {}).get("matchday") or 0,
        blend=analysis.get("blend"),
    )


def _score_pick_value(
    scoreline: str,
    rank: int,
    odd: float,
    blend: dict[str, float],
    analysis: dict,
    *,
    is_upset: bool = False,
) -> float:
    implied = (1 / odd) if odd > 0 else 0
    model_w = max(0.12, 0.55 - rank * 0.14)
    outcome = _outcome_from_score(scoreline)
    blend_pct = blend.get(outcome, 33.0)
    fav_outcome = max(blend, key=blend.get)
    model_p = model_w + blend_pct / 100 * 0.10
    edge = model_p - implied
    # Purchase plan: favour likelihood over longshot CRS value
    value = model_w * 55 + edge * 35

    if outcome != fav_outcome:
        value -= 8
    if is_upset:
        value -= 40

    if odd > 35:
        value -= 22
    elif odd > 22:
        value -= 12
    elif odd > 15:
        value -= 5
    elif 4 <= odd <= 14:
        value += 3

    alerts = analysis.get("alerts") or []
    if any("平局" in a or "默契" in a for a in alerts) and outcome != "draw":
        value -= 4
    if any("冷门" in a for a in alerts) and is_upset:
        value -= 6

    return value


def _build_score_reason(
    scoreline: str,
    odds: float,
    rank: int,
    model_scores: list[str],
    analysis: dict,
) -> str:
    parts: list[str] = []
    if rank == 0:
        parts.append(f"模型首推比分 {scoreline}")
    else:
        parts.append(f"模型预测比分 {scoreline}（第{rank + 1}候选）")

    alts = [s for s in model_scores if s != scoreline][:2]
    if alts:
        parts.append(f"其他可能比分 {' / '.join(alts)}")

    refs = analysis.get("references", {})
    teams = refs.get("teams", {})
    ta, tb = teams.get("team_a", {}), teams.get("team_b", {})
    if ta.get("available") and tb.get("available"):
        rank_a, rank_b = ta.get("rank"), tb.get("rank")
        if rank_a and rank_b:
            parts.append(f"FIFA排名 {rank_a} vs {rank_b}")

    ai = refs.get("models", {}).get("ai")
    if ai:
        parts.append(f"AI融合{ai.get('model', 'auto')} 胜/平/负 {ai.get('win', 0):.0f}/{ai.get('draw', 0):.0f}/{ai.get('lose', 0):.0f}%")
    else:
        rule = refs.get("models", {}).get("rule_engine", {})
        if rule:
            parts.append(
                f"规则引擎 胜/平/负 {rule.get('win', 0):.0f}/{rule.get('draw', 0):.0f}/{rule.get('lose', 0):.0f}%"
            )

    implied = (1 / odds * 100) if odds > 0 else 0
    parts.append(f"体彩CRS赔率 {odds:.2f}（隐含约 {implied:.1f}%）")

    alerts = analysis.get("alerts") or []
    if alerts:
        parts.append(alerts[0])

    return "；".join(parts[:4])


def _calc_score_confidence(
    analysis: dict,
    scoreline: str,
    rank: int,
    model_scores: list[str],
    *,
    crs_odd: float | None = None,
    is_upset: bool = False,
) -> float:
    refs = analysis.get("references", {})
    teams = refs.get("teams", {})
    ai = refs.get("models", {}).get("ai")
    return compute_score_confidence(
        scoreline=scoreline,
        rank=rank,
        model_scores=model_scores,
        crs_odd=crs_odd,
        blend=analysis.get("blend"),
        confidence_penalty=analysis.get("confidence_penalty", 0),
        alerts=analysis.get("alerts"),
        ai_confidence=float(ai["confidence"]) if ai and ai.get("confidence") else None,
        teams_available=bool(
            teams.get("team_a", {}).get("available") and teams.get("team_b", {}).get("available")
        ),
        matchday=analysis.get("matchday") or refs.get("match_context", {}).get("matchday") or 0,
        is_upset=is_upset,
    )


def _build_single_pick(
    st_match: dict,
    db_match: Optional[Match],
    analysis: dict,
) -> Optional[dict]:
    from data.worldcup_venues import canonical_team_order

    st_home, st_away = st_match["home_team"], st_match["away_team"]
    if db_match:
        home, away = canonical_team_order(db_match.team_a, db_match.team_b)
        odds_team_a, odds_team_b = db_match.team_a, db_match.team_b
    else:
        home, away = st_home, st_away
        odds_team_a, odds_team_b = home, away

    st_for_odds = find_sporttery_match(
        odds_team_a, odds_team_b, st_match.get("kickoff"), [st_match], league_hint=""
    ) or st_match
    odds_row = to_db_odds(st_for_odds, odds_team_a, odds_team_b)
    if not odds_row:
        return None

    crs_odds = _clean_crs_odds(odds_row.get("score_odds") or {})
    if not crs_odds:
        return None

    blend = analysis.get("blend", {"win": 33.3, "draw": 33.3, "lose": 33.4})
    prediction = analysis.get("prediction")

    pipeline_crs: dict[str, float] = {}
    sp_win: Optional[float] = None
    sp_draw: Optional[float] = None
    sp_lose: Optional[float] = None
    handicap: Optional[str] = None
    teams = analysis.get("teams") or {}
    rank_a = teams.get("team_a", {}).get("rank")
    rank_b = teams.get("team_b", {}).get("rank")

    if db_match:
        db_crs = _clean_crs_odds((analysis.get("db_fused") or {}).get("score_odds") or {})
        if db_crs:
            pipeline_crs = db_crs
        db_sp = analysis.get("db_spf") or {}
        sp_win = db_sp.get("win_win")
        sp_draw = db_sp.get("draw")
        sp_lose = db_sp.get("win_lose")
        handicap = db_sp.get("handicap")
    else:
        sp_win = odds_row.get("win_win")
        sp_draw = odds_row.get("draw")
        sp_lose = odds_row.get("win_lose")
        handicap = odds_row.get("handicap")
        pipeline_crs = crs_odds

    from utils.score_prediction import reconcile_prediction_view
    from service.prediction_consistency import sync_reason_with_view

    model_hints: list[str] = []
    stored_upset: Optional[str] = None
    if prediction and prediction.best_score:
        payload = _parse_best_score_payload(prediction.best_score)
        model_hints = payload.get("scores") or []
        u = payload.get("upset")
        stored_upset = u if u and u != "?" else None
    if not model_hints:
        model_hints = _collect_likely_scores(analysis, exclude_upset=None)

    if prediction:
        win_rate = prediction.win_rate or 50.0
        draw_rate = prediction.draw_rate if prediction.draw_rate is not None else max(
            0.0, 100.0 - (prediction.win_rate or 0) - (prediction.lose_rate or 0),
        )
        lose_rate = prediction.lose_rate or 50.0
    else:
        win_rate = blend.get("win", 33.3)
        draw_rate = blend.get("draw", 33.3)
        lose_rate = blend.get("lose", 33.4)

    if model_hints:
        norm = reconcile_prediction_view(
            model_hints, stored_upset, win_rate, draw_rate, lose_rate,
        )
    elif pipeline_crs:
        from service.score_pick import canonical_score_recommendations
        likely_scores, upset_score = canonical_score_recommendations(
            pipeline_crs,
            win_rate=win_rate,
            draw_rate=draw_rate,
            lose_rate=lose_rate,
            model_scores=None,
            sp_win=sp_win,
            sp_draw=sp_draw,
            sp_lose=sp_lose,
            handicap=handicap,
            rank_a=rank_a,
            rank_b=rank_b,
        )
        norm = reconcile_prediction_view(
            likely_scores, upset_score, win_rate, draw_rate, lose_rate,
        )
    else:
        norm = reconcile_prediction_view(
            model_hints, stored_upset, win_rate, draw_rate, lose_rate,
        )

    canonical_likely = norm["best_scores"]
    canonical_upset = norm.get("upset_score")
    norm["reason"] = sync_reason_with_view(
        (prediction.reason if prediction else None),
        home,
        away,
        norm,
    )
    blend = {
        "win": norm["win_rate"],
        "draw": norm["draw_rate"],
        "lose": norm["lose_rate"],
    }

    display_crs = {**pipeline_crs, **crs_odds}
    score_picks = _build_score_picks(
        canonical_likely, canonical_upset, display_crs, blend, analysis,
        sporttery_crs=crs_odds,
    )
    if not score_picks or not canonical_likely:
        return None

    likely_only = [p for p in score_picks if p["type"] == "likely"]
    upset_only = next((p for p in score_picks if p["type"] == "upset"), None)

    bet_likely = next((p for p in likely_only if p.get("has_sporttery_odd") and p["odds"] > 0), None)
    if not bet_likely:
        bet_likely = next((p for p in likely_only if p["odds"] > 0), likely_only[0] if likely_only else None)
    if not bet_likely:
        return None

    pick_score = bet_likely["score"]
    pick_odd = bet_likely["odds"]
    pick_rank = bet_likely["rank"] - 1
    reason = _build_score_reason(pick_score, pick_odd, pick_rank, canonical_likely, analysis)
    if len(canonical_likely) >= 2:
        reason += f"；次可能比分 {canonical_likely[1]}"
    if canonical_upset:
        reason += f"；冷门参考 {canonical_upset}"
    conf = _calc_score_confidence(
        analysis, pick_score, pick_rank, canonical_likely,
        crs_odd=pick_odd, is_upset=False,
    )

    alt_scores: list[dict] = []
    if len(canonical_likely) >= 2:
        s2 = canonical_likely[1]
        alt_scores.append({
            "score": s2,
            "odds": display_crs.get(s2) or crs_odds.get(s2) or 0.0,
            "is_upset": False,
            "type": "likely",
            "rank": 2,
        })
    if canonical_upset:
        alt_scores.append({
            "score": canonical_upset,
            "odds": display_crs.get(canonical_upset) or crs_odds.get(canonical_upset) or 0.0,
            "is_upset": True,
            "type": "upset",
            "rank": 1,
        })

    prediction = analysis.get("prediction")
    resolved_upset = canonical_upset

    return {
        "match_id": db_match.id if db_match else None,
        "match_num": st_match.get("match_num"),
        "team_a": home,
        "team_b": away,
        "kickoff": st_match["kickoff"].isoformat() if st_match.get("kickoff") else None,
        "league": st_match.get("league") or "",
        "play_type": "比分",
        "handicap": None,
        "pick": pick_score,
        "pick_code": "score",
        "score_pick": pick_score,
        "score_picks": score_picks,
        "alt_scores": alt_scores,
        "odds": pick_odd,
        "bet": _bet_payout(pick_odd),
        "confidence": conf,
        "model_win_rate": blend["win"],
        "model_draw_rate": blend["draw"],
        "model_lose_rate": blend["lose"],
        "model_scores": canonical_likely,
        "upset_score": resolved_upset,
        "reason": reason,
        "best_score": prediction.best_score if prediction else None,
        "references": analysis.get("references"),
        "data_sources": (analysis.get("references") or {}).get("data_sources", []),
    }


def _parlay_pick_row(p: dict) -> dict:
    return {
        "match_num": p["match_num"],
        "team_a": p["team_a"],
        "team_b": p["team_b"],
        "kickoff": p.get("kickoff"),
        "play_type": p["play_type"],
        "pick_code": p.get("pick_code", "score"),
        "handicap": p.get("handicap"),
        "pick": p["pick"],
        "odds": p["odds"],
    }


def _build_parlays(singles: list[dict]) -> list[dict]:
    if len(singles) < 2:
        return []

    ranked = sorted(singles, key=lambda s: (s["confidence"], -s["odds"]), reverse=True)
    stable = sorted(singles, key=lambda s: (s["confidence"], -abs(s["odds"] - 9)), reverse=True)

    parlays: list[dict] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    def _match_key(picks: list[dict]) -> tuple[str, ...]:
        return tuple(sorted(p.get("match_num") or "" for p in picks))

    def _pack(picks: list[dict], ptype: str, name_key: str, reason_key: str) -> None:
        key = (ptype, _match_key(picks))
        if key in seen:
            return
        seen.add(key)
        combined = round(prod([p["odds"] for p in picks]), 2)
        parlays.append({
            "type": ptype,
            "fold": len(picks),
            "name_key": name_key,
            "reason_key": reason_key,
            "picks": [_parlay_pick_row(p) for p in picks],
            "combined_odds": combined,
            "bet": _bet_payout(combined),
            "score_summary": " / ".join(p["pick"] for p in picks),
            "avg_confidence": round(mean([p["confidence"] for p in picks]), 2),
        })

    # 2串1
    if len(stable) >= 2:
        _pack(stable[:2], "2串1", "stable", "stableReason")
    if len(ranked) >= 2:
        _pack(ranked[:2], "2串1", "value", "valueReason")

    # 3串1+
    if len(stable) >= 3:
        _pack(stable[:3], "3串1", "tripleStable", "tripleStableReason")
    if len(ranked) >= 3:
        _pack(ranked[:3], "3串1", "triple", "tripleReason")
    if len(ranked) >= 4:
        _pack(ranked[:4], "4串1", "quad", "quadReason")
    if len(ranked) >= 5:
        _pack(ranked[:5], "5串1", "penta", "pentaReason")

    return parlays


async def get_today_sporttery_plan(db: AsyncSession, competition_slug: str = "worldcup-2026") -> dict:
    today = china_today()
    sporttery_pool = await fetch_sporttery_on_sale(force_refresh=True)
    fetch_status = get_sporttery_fetch_status()
    hints = league_hints_for(competition_slug) or WORLD_CUP_LEAGUE_HINTS
    comp = get_competition(competition_slug)
    league_label = comp["short_name"] if comp else "赛事"
    is_club = comp.get("type") == "club"

    today_matches: list[dict] = []
    seen_nums: set[str] = set()
    for st in sporttery_pool:
        if not _is_purchasable_today(st, today):
            continue
        kickoff = st.get("kickoff")
        if kickoff and kickoff.date() < today:
            continue
        league = st.get("league") or ""
        league_ok = _is_competition_league(league, hints)
        db_m = await _find_db_match(
            db, st["home_team"], st["away_team"], kickoff, competition_slug,
        )

        if league_ok:
            if is_club and not db_m:
                continue
        elif not db_m:
            continue

        num = st.get("match_num") or ""
        if num in seen_nums:
            continue
        seen_nums.add(num)
        today_matches.append(st)

    if not today_matches:
        db_upcoming = (await db.execute(
            select(Match).where(
                Match.competition_slug == competition_slug,
                Match.status.in_(match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)),
            )
        )).scalars().all()
        for m in db_upcoming:
            if not m.match_time:
                continue
            if m.match_time.date() < today:
                continue
            hit = find_sporttery_match(
                m.team_a, m.team_b, m.match_time, sporttery_pool,
                league_hints=hints,
            )
            if hit and _is_purchasable_today(hit, today):
                num = hit.get("match_num") or ""
                if num not in seen_nums:
                    seen_nums.add(num)
                    today_matches.append(hit)

    db_by_st: dict[int, Match] = {}
    match_ids: list[int] = []
    for i, st in enumerate(today_matches):
        dm = await _find_db_match(db, st["home_team"], st["away_team"], st.get("kickoff"), competition_slug)
        if dm:
            db_by_st[i] = dm
            match_ids.append(dm.id)

    preds = await _latest_predictions(db, match_ids)

    singles: list[dict] = []
    for i, st in enumerate(today_matches):
        dm = db_by_st.get(i)
        if is_club and not dm:
            continue
        pred = preds.get(dm.id) if dm else None

        from data.worldcup_venues import canonical_team_order
        if dm:
            home, away = canonical_team_order(dm.team_a, dm.team_b)
            odds_a, odds_b = dm.team_a, dm.team_b
        else:
            home, away = st["home_team"], st["away_team"]
            odds_a, odds_b = home, away
        st_for_odds = find_sporttery_match(odds_a, odds_b, st.get("kickoff"), [st], league_hint="") or st
        sporttery_odds = to_db_odds(st_for_odds, odds_a, odds_b) or {}

        analysis = await _build_match_analysis(db, dm, pred, sporttery_odds)
        pick = _build_single_pick(st, dm, analysis)
        if pick:
            singles.append(pick)

    singles.sort(key=lambda s: s.get("kickoff") or "")

    if singles:
        empty_reason = None
    elif not sporttery_pool and fetch_status.get("last_error"):
        empty_reason = "sporttery_unreachable"
    elif not today_matches:
        empty_reason = "today_no_on_sale"
    else:
        empty_reason = "no_score_odds"

    parlays = _build_parlays(singles)

    return {
        "date": today.isoformat(),
        "updated_at": datetime.now().isoformat(),
        "on_sale_count": len(singles),
        "singles": singles,
        "parlays": parlays,
        "parlay_folds": sorted({p["fold"] for p in parlays}),
        "default_stake_yuan": DEFAULT_STAKE_YUAN,
        "empty_reason": empty_reason,
        "today_only": True,
        "sporttery_status": fetch_status,
        "sporttery_pool_size": len(sporttery_pool),
        "today_match_candidates": len(today_matches),
        "competition_slug": competition_slug,
        "methodology": {
            "description": "基于体彩官方CRS比分赔率，融合球队能力、外围盘口、规则引擎与AI预测比分",
            "weights": _BLEND_WEIGHTS,
        },
    }
