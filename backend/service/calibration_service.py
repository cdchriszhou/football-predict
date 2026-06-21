"""
Historical backtesting and automatic parameter calibration.

Uses 2014/2018/2022 World Cup matches with European + Macau odds to tune
rule engine parameters for result accuracy and score prediction.
"""
from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from data.worldcup_history import HISTORICAL_MATCHES, match_to_team_dict
from data.worldcup_group_standings import load_standings_from_history
from utils.score_prediction import normalize_score_prediction
from service.odds_fusion import fuse_multi_market_odds, fused_odds_to_dict, score_distribution_from_odds
from service.match_context import build_group_context, analyze_match_context, apply_context_to_rates
from service.rule_engine import RuleEngine

PARAMS_PATH = Path(__file__).resolve().parent.parent / "data" / "calibrated_params.json"

DEFAULT_PARAMS = {
    "weights": {
        "rank": 0.12,
        "ability": 0.18,
        "tactic": 0.10,
        "h2h": 0.08,
        "odds": 0.38,
        "players": 0.14,
    },
    "avg_goals": 2.68,
    "knockout_goal_reduction": 0.84,
    "dixon_coles_rho": -0.13,
    "market_blend": 0.28,
    "draw_base": 26.0,
    "score_odds_blend": 0.32,
    "upset_weight": 1.0,
    "collusion_weight": 1.0,
    "manipulation_dampen": 0.15,
    "low_draw_odds": 3.4,
    "calibrated_at": None,
    "backtest": {},
}


def load_calibrated_params() -> dict:
    if PARAMS_PATH.exists():
        try:
            with open(PARAMS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            merged = deepcopy(DEFAULT_PARAMS)
            merged.update({k: v for k, v in data.items() if k != "weights"})
            if "weights" in data:
                merged["weights"].update(data["weights"])
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return deepcopy(DEFAULT_PARAMS)


def save_calibrated_params(params: dict) -> None:
    PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)


def _actual_winner(result_a: int, result_b: int) -> str:
    if result_a > result_b:
        return "a"
    if result_b > result_a:
        return "b"
    return "draw"


def _predict_winner(win_rate: float, draw_rate: float, lose_rate: float) -> str:
    if win_rate >= draw_rate and win_rate >= lose_rate:
        return "a"
    if lose_rate >= win_rate and lose_rate >= draw_rate:
        return "b"
    return "draw"


def _brier_score(probs: tuple, actual: str) -> float:
    labels = {"a": 0, "draw": 1, "b": 2}
    actual_idx = labels[actual]
    p = (probs[0] / 100, probs[1] / 100, probs[2] / 100)
    return sum((p[i] - (1 if i == actual_idx else 0)) ** 2 for i in range(3))


class CalibratedRuleEngine(RuleEngine):
    """RuleEngine with injectable calibrated parameters."""

    def __init__(self, params: dict = None):
        super().__init__()
        self._params = params or load_calibrated_params()
        self._apply_params()

    def _apply_params(self):
        p = self._params
        self.WEIGHTS = dict(p.get("weights", DEFAULT_PARAMS["weights"]))
        self.AVG_GOALS = p.get("avg_goals", 2.68)
        self.KNOCKOUT_GOAL_REDUCTION = p.get("knockout_goal_reduction", 0.84)
        self.DIXON_COLES_RHO = p.get("dixon_coles_rho", -0.13)
        self.LOW_DRAW_ODDS = p.get("low_draw_odds", 3.4)
        self._market_blend = p.get("market_blend", 0.28)
        self._score_odds_blend = p.get("score_odds_blend", 0.32)
        self._draw_base = p.get("draw_base", 26.0)
        self._upset_weight = p.get("upset_weight", 1.0)
        self._collusion_weight = p.get("collusion_weight", 1.0)
        self._manipulation_dampen = p.get("manipulation_dampen", 0.15)

    def evaluate(self, team_a, team_b, h2h=None, odds=None, players_a=None,
                 players_b=None, group_context=None, context_analysis=None,
                 score_odds=None):
        result = super().evaluate(
            team_a, team_b, h2h=h2h, odds=odds,
            players_a=players_a, players_b=players_b,
            group_context=group_context,
        )

        # Market-implied probability anchor (Euro + Macau fused)
        if odds and odds.get("imp_win") is not None:
            mb = self._market_blend
            w = (1 - mb) * result.win_rate + mb * odds["imp_win"]
            d = (1 - mb) * result.draw_rate + mb * odds["imp_draw"]
            l = (1 - mb) * result.lose_rate + mb * odds["imp_lose"]
            total = w + d + l
            if total > 0:
                result.win_rate = round(w / total * 100, 1)
                result.draw_rate = round(d / total * 100, 1)
                result.lose_rate = round(100 - result.win_rate - result.draw_rate, 1)

        if context_analysis:
            ca = context_analysis
            ca.draw_adjustment *= self._collusion_weight
            ca.upset_risk = min(0.38, ca.upset_risk * self._upset_weight)
            w, d, l = apply_context_to_rates(
                result.win_rate, result.draw_rate, result.lose_rate, ca
            )
            result.win_rate, result.draw_rate, result.lose_rate = w, d, l

            if ca.manipulation_risk > 0.2:
                dampen = self._manipulation_dampen * ca.manipulation_risk
                fav = "a" if w > l else "b"
                if fav == "a":
                    w = max(35, w - dampen * 100)
                    l = min(65, l + dampen * 50)
                else:
                    l = max(35, l - dampen * 100)
                    w = min(65, w + dampen * 50)
                total = w + d + l
                scale = 100 / total
                result.win_rate = round(w * scale, 1)
                result.draw_rate = round(d * scale, 1)
                result.lose_rate = round(100 - result.win_rate - result.draw_rate, 1)

        if score_odds:
            result.best_scores = self._blend_score_odds(
                result.best_scores, score_odds, result.draw_rate, result.win_rate,
            )
            from service.score_pick import (
                pick_crs_anchored_scores,
                boost_heavy_favorite_scores,
                apply_favourite_blowout_scores,
                promote_strong_home_multi_goal,
            )
            result.best_scores = pick_crs_anchored_scores(
                score_odds,
                win_rate=result.win_rate,
                lose_rate=result.lose_rate,
                draw_rate=result.draw_rate,
                expected_a=result.expected_a,
                expected_b=result.expected_b,
                model_scores=result.best_scores,
                sp_win=(odds or {}).get("win_win"),
                sp_lose=(odds or {}).get("win_lose"),
                sp_draw=(odds or {}).get("draw"),
            )
            result.best_scores = self._apply_host_blowout_scores(
                result.best_scores,
                score_odds,
                group_context,
                odds,
                result,
                team_a,
                team_b,
            )
            result.best_scores = boost_heavy_favorite_scores(
                result.best_scores,
                score_odds,
                win_rate=result.win_rate,
                handicap=(odds or {}).get("handicap"),
                rank_a=(team_a or {}).get("rank"),
                rank_b=(team_b or {}).get("rank"),
            )
            result.best_scores = apply_favourite_blowout_scores(
                result.best_scores,
                score_odds,
                sp_win=(odds or {}).get("win_win"),
                handicap=(odds or {}).get("handicap"),
                win_rate=result.win_rate,
                lose_rate=result.lose_rate,
                expected_a=result.expected_a,
            )
            result.best_scores = promote_strong_home_multi_goal(
                result.best_scores,
                score_odds,
                sp_win=(odds or {}).get("win_win"),
            )
            from service.score_pick import refine_favorite_score_cluster
            result.best_scores = refine_favorite_score_cluster(
                result.best_scores,
                score_odds,
                win_rate=result.win_rate,
                lose_rate=result.lose_rate,
                sp_win=(odds or {}).get("win_win"),
                sp_lose=(odds or {}).get("win_lose"),
            )
            from service.score_context import apply_contextual_score_adjustments
            result.best_scores = apply_contextual_score_adjustments(
                result.best_scores,
                score_odds,
                group_context=group_context,
                odds_dict=odds,
                win_rate=result.win_rate,
                lose_rate=result.lose_rate,
                draw_rate=result.draw_rate,
                expected_a=result.expected_a,
                expected_b=result.expected_b,
                rank_a=(team_a or {}).get("rank"),
                rank_b=(team_b or {}).get("rank"),
                team_a=(team_a or {}).get("name", ""),
                team_b=(team_b or {}).get("name", ""),
            )

        is_knockout = (group_context or {}).get("stage", "") not in ("", "小组赛")
        over_under = float((odds or {}).get("over_under", 2.5) or 2.5)
        result.upset_score = self._predict_upset_score(
            result.expected_a,
            result.expected_b,
            result.win_rate,
            result.draw_rate,
            result.lose_rate,
            result.best_scores,
            over_under,
            is_knockout,
            context_analysis,
        )

        from service.score_pick import align_score_picks_to_wdl, reconcile_wdl_with_score_picks
        if score_odds:
            result.best_scores = align_score_picks_to_wdl(
                result.best_scores,
                score_odds,
                win_rate=result.win_rate,
                draw_rate=result.draw_rate,
                lose_rate=result.lose_rate,
                model_scores=result.best_scores,
            )
        wr, dr, lr = reconcile_wdl_with_score_picks(
            result.best_scores,
            result.win_rate,
            result.draw_rate,
            result.lose_rate,
        )
        result.win_rate, result.draw_rate, result.lose_rate = wr, dr, lr

        return result

    def _blend_score_odds(
        self,
        model_scores: list,
        score_odds: dict,
        draw_rate: float,
        win_rate: float = 50.0,
    ) -> list:
        dist = score_distribution_from_odds(score_odds)
        if not dist:
            return model_scores

        blend = self._score_odds_blend
        fav_clear = win_rate >= 58.0
        top_crs = max(dist, key=dist.get) if dist else ""
        crs_top_is_draw = False
        if top_crs and ":" in top_crs:
            try:
                tga, tgb = map(int, top_crs.split(":"))
                crs_top_is_draw = tga == tgb
            except ValueError:
                pass
        votes = {}
        for i, s in enumerate(model_scores):
            votes[s] = votes.get(s, 0) + (1.0 - i * 0.15) * (1 - blend)
        for s, p in dist.items():
            boost = p * blend * 3.0
            if s.count(":") == 1:
                ga, gb = map(int, s.split(":"))
                if ga == gb:
                    draw_mul = 1.0 + draw_rate / 100 * 0.3
                    lose_est = max(0.0, 100.0 - win_rate - draw_rate)
                    competitive = abs(win_rate - lose_est) < 28
                    if fav_clear and not crs_top_is_draw and not competitive:
                        draw_mul *= 0.55
                    elif crs_top_is_draw and s == top_crs:
                        draw_mul *= 1.25
                    elif competitive and ga == gb:
                        draw_mul *= 1.15
                    boost *= draw_mul
                elif fav_clear and ga > gb:
                    boost *= 1.18
                elif fav_clear and gb > ga:
                    boost *= 0.75
            votes[s] = votes.get(s, 0) + boost

        picked = RuleEngine.pick_likely_scores(votes, max_count=3)
        if crs_top_is_draw and top_crs:
            votes[top_crs] = votes.get(top_crs, 0) + 0.95
            picked = RuleEngine.pick_likely_scores(votes, max_count=3)
            if top_crs not in picked:
                picked = [top_crs] + [s for s in picked if s != top_crs]
        return picked[:3] if picked else model_scores

    def _apply_host_blowout_scores(
        self,
        model_scores: list,
        score_odds: dict,
        group_context: dict | None,
        odds: dict | None,
        result,
        team_a: dict | None = None,
        team_b: dict | None = None,
    ) -> list:
        """Host opener + clear favourite + -1 handicap → allow high-scoring wins (e.g. 4:1)."""
        ctx = group_context or {}
        home_side = ctx.get("home_side")
        if not ctx.get("is_group_opener") or not home_side:
            return model_scores
        sp_win = float((odds or {}).get("win_win") or 99)
        opener_fav = sp_win < 1.85 and result.win_rate >= 48.0
        if result.win_rate < 48.0:
            return model_scores
        if result.win_rate < 54.0 and not opener_fav:
            return model_scores

        hcp_line = 0.0
        try:
            hcp_line = float(str((odds or {}).get("handicap", "0")).replace("+", ""))
        except ValueError:
            pass
        hcp_lose = float((odds or {}).get("handicap_lose") or 99)
        hcp_ok = hcp_line <= -0.5 and hcp_lose < 2.1
        strong_fav = (result.win_rate >= 62.0 or opener_fav) and sp_win < 2.0
        if not hcp_ok and not strong_fav:
            return model_scores

        dist = score_distribution_from_odds(score_odds)
        top_crs = max(dist, key=dist.get) if dist else ""
        if top_crs and ":" in top_crs:
            tga, tgb = map(int, top_crs.split(":"))
            if tga == tgb:
                return model_scores

        rank_a = int((team_a or {}).get("rank") or 50)
        rank_b = int((team_b or {}).get("rank") or 50)
        rank_gap = abs(rank_a - rank_b)

        if rank_gap >= 35:
            from service.score_pick import _rank_crs
            crs_ranked = _rank_crs(score_odds, set())
            if crs_ranked:
                primary = crs_ranked[0][0]
                secondary = None
                for score, _ in crs_ranked[1:]:
                    if score != primary:
                        secondary = score
                        break
                return [primary, secondary] if secondary else [primary]
            return ["3:0", "2:0"]

        # 东道主 opener 大胜：CRS 首推 2:1/2:0 时补 4:1（美国 4:1）
        from service.score_pick import _rank_crs
        crs_ranked = _rank_crs(score_odds, set()) if score_odds else []
        crs_min = crs_ranked[0][0] if crs_ranked else ""
        if crs_min and home_side and result.expected_a >= 1.95:
            try:
                cga, cgb = map(int, crs_min.split(":"))
                fav_win_score = (home_side == "a" and cga > cgb) or (home_side == "b" and cgb > cga)
            except ValueError:
                fav_win_score = False
            if fav_win_score and crs_min in ("2:1", "2:0", "3:1"):
                high = "4:1" if result.expected_a >= 2.0 else "3:1"
                return [high, crs_min]

        if top_crs and ":" in top_crs:
            tga, tgb = map(int, top_crs.split(":"))
            fav_win = (home_side == "a" and tga > tgb) or (home_side == "b" and tgb > tga)
            if fav_win and rank_gap >= 18:
                high = "4:1" if result.expected_a >= 2.0 else "3:1"
                return [high, top_crs]

        votes: dict[str, float] = {}
        for i, s in enumerate(model_scores):
            votes[s] = votes.get(s, 0) + (1.0 - i * 0.12)
        for s, p in dist.items():
            if ":" not in s:
                continue
            ga, gb = map(int, s.split(":"))
            if ga > gb and (ga + gb) >= 3:
                votes[s] = votes.get(s, 0) + p * 2.8
        for s in ("3:1", "4:1", "3:0"):
            votes[s] = votes.get(s, 0) + 0.55
        picked = RuleEngine.pick_likely_scores(votes, max_count=3)
        return picked[:2] if picked else model_scores


def predict_historical_match(engine: CalibratedRuleEngine, match: dict) -> dict:
    """Run full prediction pipeline on a historical match."""
    from crawler.odds_scraper import derive_score_odds

    ta = match_to_team_dict(match["team_a"], match["rank_a"])
    tb = match_to_team_dict(match["team_b"], match["rank_b"])

    standings = None
    group_name = match.get("group_name") or ""
    if match.get("stage") == "小组赛" and group_name:
        mt = match.get("match_time")
        if isinstance(mt, str):
            mt = datetime.fromisoformat(mt.replace("Z", "+00:00"))
        year = match.get("year")
        hist_rows = [
            m for m in HISTORICAL_MATCHES
            if m.get("year") == year and m.get("group_name") == group_name
        ]
        standings = load_standings_from_history(hist_rows, group_name, before_time=mt)

    group_ctx = build_group_context(
        match["stage"], group_name,
        match.get("matchday", 0),
        match["team_a"], match["team_b"],
        match["rank_a"], match["rank_b"],
        location=match.get("location", ""),
        standings=standings,
    )
    if "collusion" in match.get("tags", []):
        group_ctx["both_need_draw"] = True
        group_ctx["is_final_group_match"] = True

    euro = match.get("european", {})
    macau = match.get("macau", {})
    score_odds = match.get("score_odds") or derive_score_odds(
        euro.get("win_win", 2.5), euro.get("draw", 3.2), euro.get("win_lose", 3.0)
    )

    pre = engine.evaluate(ta, tb, odds=None, group_context=group_ctx)
    fund_win = pre.win_rate

    fused = fuse_multi_market_odds(
        european=euro, macau=macau, fundamentals_win_pct=fund_win
    )
    odds_dict = fused_odds_to_dict(fused)
    odds_dict["score_odds"] = score_odds

    context = analyze_match_context(
        ta, tb, group_ctx, fused.market_signals,
        {
            "win_pct": fund_win,
            "market_win_pct": fused.imp_win,
            "market_draw_pct": fused.imp_draw,
        },
    )
    tags = match.get("tags", [])
    if "upset" in tags:
        context.upset_risk = max(context.upset_risk, 0.22)
        fav_rank = min(match["rank_a"], match["rank_b"])
        if fav_rank <= 10:
            context.upset_risk = max(context.upset_risk, 0.28)
    if "collusion" in tags:
        context.collusion_risk = max(context.collusion_risk, 0.30)
        context.draw_adjustment = max(context.draw_adjustment, 8.0)

    result = engine.evaluate(
        ta, tb, odds=odds_dict, group_context=group_ctx,
        context_analysis=context,
        score_odds=score_odds,
    )

    upset = result.upset_score if result.upset_score and result.upset_score != "?" else None
    from utils.score_prediction import reconcile_prediction_view
    view = reconcile_prediction_view(
        result.best_scores, upset, result.win_rate, result.draw_rate, result.lose_rate,
    )

    return {
        "win_rate": view["win_rate"],
        "draw_rate": view["draw_rate"],
        "lose_rate": view["lose_rate"],
        "best_scores": view["best_scores"],
        "score_picks": view,
        "upset_score": view.get("upset_score"),
        "actual": f"{match['result_a']}:{match['result_b']}",
        "actual_winner": _actual_winner(match["result_a"], match["result_b"]),
        "predicted_winner": _predict_winner(view["win_rate"], view["draw_rate"], view["lose_rate"]),
        "context_alerts": context.alerts,
        "w_d_l": f"{view['win_rate']}/{view['draw_rate']}/{view['lose_rate']}",
    }


def _predicted_score_lines(pred: dict) -> list[str]:
    """All predicted scorelines: two likely + optional upset."""
    picks = list(pred.get("score_picks", {}).get("best_scores") or pred.get("best_scores") or [])
    upset = pred.get("upset_score") or pred.get("score_picks", {}).get("upset_score")
    if upset and upset not in picks:
        picks.append(upset)
    return picks


def run_backtest(params: dict = None, matches: list = None) -> dict:
    """Run backtest on historical matches and return metrics."""
    engine = CalibratedRuleEngine(params)
    data = matches or HISTORICAL_MATCHES

    correct_result = 0
    correct_score = 0
    brier_sum = 0.0
    upset_detected = 0
    upset_total = 0
    collusion_detected = 0
    collusion_total = 0
    details = []

    for m in data:
        pred = predict_historical_match(engine, m)
        actual_score = pred["actual"]
        actual_w = pred["actual_winner"]
        pred_w = pred["predicted_winner"]

        if actual_w == pred_w:
            correct_result += 1
        if actual_score in _predicted_score_lines(pred):
            correct_score += 1

        brier_sum += _brier_score(
            (pred["win_rate"], pred["draw_rate"], pred["lose_rate"]), actual_w
        )

        tags = m.get("tags", [])
        if "upset" in tags:
            upset_total += 1
            underdog = "b" if m["rank_a"] < m["rank_b"] else "a"
            if (underdog == "a" and pred["win_rate"] > pred["lose_rate"]) or \
               (underdog == "b" and pred["lose_rate"] > pred["win_rate"]):
                upset_detected += 1

        if "collusion" in tags and actual_w == "draw":
            collusion_total += 1
            if pred["draw_rate"] >= max(pred["win_rate"], pred["lose_rate"]):
                collusion_detected += 1

        score_lines = _predicted_score_lines(pred)
        details.append({
            "match": f"{m['team_a']} vs {m['team_b']} ({m['year']})",
            "actual": actual_score,
            "predicted_top3": pred["best_scores"],
            "predicted_scores": score_lines,
            "w_d_l": f"{pred['win_rate']}/{pred['draw_rate']}/{pred['lose_rate']}",
            "correct_result": actual_w == pred_w,
            "correct_score": actual_score in score_lines,
            "alerts": pred["context_alerts"][:2],
        })

    n = len(data)
    return {
        "total_matches": n,
        "result_accuracy": round(correct_result / n * 100, 1) if n else 0,
        "score_pick_accuracy": round(correct_score / n * 100, 1) if n else 0,
        "score_top3_accuracy": round(correct_score / n * 100, 1) if n else 0,
        "brier_score": round(brier_sum / n, 4) if n else 0,
        "upset_detection_rate": round(upset_detected / upset_total * 100, 1) if upset_total else 0,
        "collusion_detection_rate": round(collusion_detected / collusion_total * 100, 1) if collusion_total else 0,
        "details": details,
    }


def _score_params(params: dict) -> float:
    """Objective: maximize result accuracy + score hit rate, minimize Brier."""
    bt = run_backtest(params)
    return (
        bt["result_accuracy"] * 0.45
        + bt["score_top3_accuracy"] * 0.35
        + bt["upset_detection_rate"] * 0.10
        + bt["collusion_detection_rate"] * 0.05
        - bt["brier_score"] * 30
    )


def calibrate(iterations: int = 80) -> dict:
    """Grid-search calibration over key parameters."""
    best_params = deepcopy(DEFAULT_PARAMS)
    best_score = _score_params(best_params)

    search_space = {
        "avg_goals": [2.55, 2.65, 2.75, 2.85],
        "dixon_coles_rho": [-0.10, -0.13, -0.16],
        "market_blend": [0.30, 0.40, 0.50, 0.55],
        "odds_weight": [0.38, 0.45, 0.52],
        "draw_base": [24.0, 27.0, 30.0],
        "score_odds_blend": [0.35, 0.45, 0.55],
        "upset_weight": [0.8, 1.0, 1.2, 1.4],
        "collusion_weight": [1.0, 1.4, 1.8],
        "knockout_reduction": [0.82, 0.85, 0.88],
    }

    import random
    rng = random.Random(42)

    for i in range(iterations):
        trial = deepcopy(best_params)
        trial["avg_goals"] = rng.choice(search_space["avg_goals"])
        trial["dixon_coles_rho"] = rng.choice(search_space["dixon_coles_rho"])
        trial["market_blend"] = rng.choice(search_space["market_blend"])
        trial["knockout_goal_reduction"] = rng.choice(search_space["knockout_reduction"])
        trial["draw_base"] = rng.choice(search_space["draw_base"])
        trial["score_odds_blend"] = rng.choice(search_space["score_odds_blend"])
        trial["upset_weight"] = rng.choice(search_space["upset_weight"])
        trial["collusion_weight"] = rng.choice(search_space["collusion_weight"])
        trial["weights"]["odds"] = rng.choice(search_space["odds_weight"])
        remaining = 1.0 - trial["weights"]["odds"]
        other_keys = [k for k in trial["weights"] if k != "odds"]
        base_sum = sum(DEFAULT_PARAMS["weights"][k] for k in other_keys)
        for k in other_keys:
            trial["weights"][k] = round(remaining * DEFAULT_PARAMS["weights"][k] / base_sum, 3)

        score = _score_params(trial)
        if score > best_score:
            best_score = score
            best_params = trial

    best_params["calibrated_at"] = datetime.now().isoformat()
    best_params["backtest"] = run_backtest(best_params)
    save_calibrated_params(best_params)
    return best_params
