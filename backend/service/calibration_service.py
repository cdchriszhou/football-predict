"""
League-prior parameter store for the rule engine.

World Cup 2014/18/22 grid-search is retired. These priors match typical
Big Five rates (~23–26% draws, ~2.7 goals/game) and trust league markets.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from service.odds_fusion import score_distribution_from_odds
from service.match_context import apply_context_to_rates
from service.rule_engine import RuleEngine

PARAMS_PATH = Path(__file__).resolve().parent.parent / "data" / "calibrated_params.json"

DEFAULT_PARAMS = {
    "source": "big-five-league",
    "weights": {
        "rank": 0.10,
        "ability": 0.16,
        "tactic": 0.08,
        "h2h": 0.06,
        "odds": 0.45,
        "players": 0.15,
    },
    "avg_goals": 2.72,
    "knockout_goal_reduction": 1.0,
    "dixon_coles_rho": -0.10,
    "market_blend": 0.40,
    "draw_base": 25.0,
    "score_odds_blend": 0.38,
    "upset_weight": 1.0,
    "collusion_weight": 1.0,
    "manipulation_dampen": 0.12,
    "low_draw_odds": 3.5,
    "KO_ROUND_PARAMS": {},
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
        self._draw_base = p.get("draw_base", 25.0)
        self.DRAW_BASE = self._draw_base  # wire to parent RuleEngine
        self._upset_weight = p.get("upset_weight", 1.0)
        self._collusion_weight = p.get("collusion_weight", 1.0)
        self._manipulation_dampen = p.get("manipulation_dampen", 0.15)
        self._ko_params = p.get("KO_ROUND_PARAMS", {})

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
            # Use the new weighted-ensemble pipeline for score selection
            from service.score_pick import run_full_score_pipeline
            best, upset, _, _ = run_full_score_pipeline(
                score_odds,
                win_rate=result.win_rate,
                draw_rate=result.draw_rate,
                lose_rate=result.lose_rate,
                expected_a=result.expected_a,
                expected_b=result.expected_b,
                model_scores=result.best_scores,
                stage=(group_context or {}).get("stage"),
                sp_win=(odds or {}).get("win_win"),
                sp_lose=(odds or {}).get("win_lose"),
                sp_draw=(odds or {}).get("draw"),
                handicap=(odds or {}).get("handicap"),
                rank_a=(team_a or {}).get("rank"),
                rank_b=(team_b or {}).get("rank"),
                group_context=group_context,
                odds_dict=odds,
                rule_result=result,
                team_a=team_a,
                team_b=team_b,
            )
            result.best_scores = best

        from service.score_pick import is_knockout_stage
        is_knockout = is_knockout_stage((group_context or {}).get("stage", ""))
        over_under = float((odds or {}).get("over_under", 2.5) or 2.5)
        if not getattr(result, 'upset_score', None) or result.upset_score == "?":
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

        from service.league_rank import GAP_LARGE, GAP_MISMATCH, rank_gap as league_rank_gap
        rank_gap = league_rank_gap((team_a or {}).get("rank"), (team_b or {}).get("rank"))

        if rank_gap >= GAP_MISMATCH:
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
            if fav_win and rank_gap >= GAP_LARGE:
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


def run_backtest(params: dict = None, matches: list = None) -> dict:
    """Return stored metrics. World Cup historical replay has been removed."""
    params = params or load_calibrated_params()
    stored = params.get("backtest") or {}
    return {
        "total_matches": stored.get("total_matches", 0),
        "result_accuracy": stored.get("result_accuracy", 0),
        "score_pick_accuracy": stored.get("score_pick_accuracy", 0),
        "score_top3_accuracy": stored.get("score_top3_accuracy", 0),
        "brier_score": stored.get("brier_score", 0),
        "upset_detection_rate": stored.get("upset_detection_rate", 0),
        "collusion_detection_rate": stored.get("collusion_detection_rate", 0),
        "details": stored.get("details") or [],
    }


def calibrate(iterations: int = 80) -> dict:
    """World Cup historical calibration retired; keep current params."""
    params = load_calibrated_params()
    save_calibrated_params(params)
    return params
