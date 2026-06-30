"""
MarketCRSScorer — SECONDARY scorer (default weight 0.30).

Converts CRS market odds to a probability distribution and applies
market-internal adjustment rules as additive weight boosts.

The market knows things the model doesn't (injuries, tactical leaks,
squad rotation). But it should VALIDATE, not DOMINATE the prediction.
"""
from __future__ import annotations

from typing import Optional

from .base import BaseScorer, ScorerInput, ScorerResult


class MarketCRSScorer(BaseScorer):
    """
    SECONDARY scorer. CRS market odds with draw-promotion, cluster-preservation,
    and favorite-refinement rules — all as additive weight adjustments.
    """

    label = "market_crs"

    def score(self, inp: ScorerInput) -> ScorerResult:
        if not inp.score_odds:
            return ScorerResult(scores={}, confidence=0.0, rationale="no CRS odds", source=self.label)

        # 1. Convert CRS odds to probability distribution
        from service.odds_fusion import score_distribution_from_odds
        crs_dist = score_distribution_from_odds(inp.score_odds)
        if not crs_dist:
            return ScorerResult(scores={}, confidence=0.0, rationale="empty CRS dist", source=self.label)

        # 2. Build ranked list for rule evaluation
        ranked = self._rank_crs(inp.score_odds, set())
        cmap = dict(ranked)

        # 3. Apply market-internal adjustment rules (additive boosts)
        dist = dict(crs_dist)
        dist = self._apply_draw_promotion_rules(dist, ranked, cmap, inp)
        dist = self._apply_cluster_rules(dist, ranked, cmap, inp)
        dist = self._apply_refinement_rules(dist, ranked, cmap, inp)

        # 4. Normalize
        normalized = self._normalize(dist)

        return ScorerResult(
            scores=normalized,
            confidence=self._compute_confidence(inp),
            rationale=f"CRS top: {ranked[0][0] if ranked else '?'}",
            source=self.label,
        )

    # ── Draw Promotion Rules ────────────────────────────────────────────

    def _apply_draw_promotion_rules(
        self, dist: dict[str, float],
        ranked: list[tuple[str, float]], cmap: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """Boost draw scores when market signals and context support it."""
        result = dict(dist)
        if not ranked:
            return result

        primary = ranked[0][0]
        pri_out = self._score_outcome(primary)
        pri_odd = cmap.get(primary, 99)
        dr = inp.draw_rate
        fav_a = inp.win_rate >= inp.lose_rate
        market_fav_a = self._market_fav_a(inp.sp_win, inp.sp_lose)
        gap_to_2nd = (ranked[1][1] - pri_odd) if len(ranked) > 1 else 99.0

        from service.score_pick_config import get_config
        cfg = get_config()
        hf_sp_win = float(cfg.get("HEAVY_FAV_SP_WIN", 1.55))
        hf_sp_lose = float(cfg.get("HEAVY_FAV_SP_LOSE", 1.55))

        # Heavy away fav + draw primary → boost close away-win over draw
        if pri_out == "draw" and self._is_heavy_fav_away(inp.lose_rate, inp.sp_lose):
            for score, odd in ranked[1:6]:
                if score == primary:
                    continue
                if self._score_outcome(score) == "lose":
                    if self._draw_close(primary, score, ranked, ratio_cap=1.15, gap_cap=1.2):
                        result[score] += result.get(score, 0) * 0.40
                        result[primary] *= 0.70
                        break

        # Competitive + slight fav + draw primary → boost margin win like 2:1
        competitive = abs(inp.win_rate - inp.lose_rate) < 32 and dr >= 16
        slight_fav = inp.win_rate < 58.0
        if (pri_out == "draw" and competitive and slight_fav
                and inp.expected_a + inp.expected_b >= 2.15
                and inp.win_rate > inp.lose_rate + 8
                and gap_to_2nd >= 0.8):
            margin_pick = self._best_margin_win(ranked, fav_a, inp, skip={primary})
            if margin_pick:
                try:
                    ga, gb = map(int, margin_pick.split(":"))
                    if abs(ga - gb) == 1 and (ga + gb) >= 3:
                        result[margin_pick] += result.get(margin_pick, 0) * 0.45
                        result[primary] *= 0.65
                except ValueError:
                    pass

        # Heavy away fav + minnow home → boost draw secondary (0:0)
        if (pri_out == "lose" and inp.sp_lose is not None and inp.sp_win is not None
                and inp.sp_lose < inp.sp_win
                and int(inp.rank_a or 50) >= 75
                and abs(int(inp.rank_a or 50) - int(inp.rank_b or 50)) >= 35):
            draw_pick = "0:0" if cmap.get("0:0") else self._best_draw(ranked, {primary})
            if draw_pick and cmap.get(draw_pick, 99) <= 12.0:
                result[draw_pick] += result.get(draw_pick, 0) * 0.50

        # Heavy away fav → boost draw over away-win primary when close
        if self._is_heavy_fav_away(inp.lose_rate, inp.sp_lose) and pri_out == "lose":
            draw_pick = self._best_draw(ranked, set())
            if draw_pick and self._draw_close(primary, draw_pick, ranked, ratio_cap=1.85, gap_cap=3.0):
                result[draw_pick] += result.get(draw_pick, 0) * 0.55
                result[primary] *= 0.70

        # Draw promotion when draw odds close to favourite win
        if pri_out != "draw":
            draw_pick = self._best_draw(ranked, {primary})
            if draw_pick and self._should_promote_draw(primary, draw_pick, ranked, inp):
                result[draw_pick] += result.get(draw_pick, 0) * 0.45
                result[primary] *= 0.75

        # Tight match + draw primary + market slightly fav home → boost home win
        # Stronger boost when odds gap is narrow (Ghana 1:0, Morocco 1:0)
        tight = self._is_competitive(inp.win_rate, inp.lose_rate)
        if pri_out == "draw" and tight and dr < 42 and inp.win_rate >= 48:
            fav_home = market_fav_a if market_fav_a is not None else fav_a
            if fav_home and not self._is_heavy_fav_home(inp.win_rate, inp.sp_win):
                home_win = self._best_home_win(ranked, {primary}, inp.expected_a)
                if home_win:
                    hw_odd = cmap.get(home_win, 99)
                    d_odd = cmap.get(primary, 99)
                    # Boost strength depends on how close home_win is to draw
                    if hw_odd < 99 and d_odd < 99 and (hw_odd - d_odd) <= 1.5:
                        # Very tight: strong home win promotion
                        result[home_win] += result.get(home_win, 0) * 0.70
                        result[primary] *= 0.55
                    elif self._home_win_close_to_draw(primary, home_win, ranked):
                        result[home_win] += result.get(home_win, 0) * 0.55
                        result[primary] *= 0.65

        # Away market fav + draw primary + 1:0 close → boost home 1:0
        if pri_out == "draw" and market_fav_a is False and inp.sp_lose and inp.sp_win:
            if inp.sp_lose < inp.sp_win - 0.2:
                d_odd = cmap.get(primary, 99)
                one_nil_odd = cmap.get("1:0", 99)
                if d_odd < 99 and one_nil_odd < 99 and (one_nil_odd - d_odd) <= 3.5:
                    result["1:0"] += result.get("1:0", 0) * 0.42
                    result[primary] *= 0.72

        # Away market fav + draw primary → boost home 1:0 as secondary
        if pri_out == "draw" and market_fav_a is False:
            for score, odd in ranked[1:8]:
                if score == primary:
                    continue
                try:
                    ga, gb = map(int, score.split(":"))
                except ValueError:
                    continue
                if ga == 1 and gb == 0 and odd <= 9.0:
                    result[score] += result.get(score, 0) * 0.35
                    break

        # Heavy home fav + draw primary → keep draw, boost small win
        if pri_out == "draw" and self._is_heavy_fav_home(inp.win_rate, inp.sp_win):
            for score, _ in ranked[1:]:
                if score == primary:
                    continue
                try:
                    ga, gb = map(int, score.split(":"))
                except ValueError:
                    continue
                if ga > gb:
                    result[score] += result.get(score, 0) * 0.38
                    break

        return result

    # ── Cluster Rules ────────────────────────────────────────────────────

    def _apply_cluster_rules(
        self, dist: dict[str, float],
        ranked: list[tuple[str, float]], cmap: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """Preserve one-nil cluster (1:0+1:1) and low-scoring patterns."""
        result = dict(dist)
        if not ranked:
            return result

        # One-nil cluster detection
        if self._is_low_scoring_win_cluster(ranked, inp.sp_draw):
            result["1:0"] = result.get("1:0", 0) * 1.30
            if cmap.get("1:1"):
                result["1:1"] = result.get("1:1", 0) * 1.20

        return result

    # ── Refinement Rules ─────────────────────────────────────────────────

    def _apply_refinement_rules(
        self, dist: dict[str, float],
        ranked: list[tuple[str, float]], cmap: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """Refine score distribution: boost alternates, suppress weak secondaries."""
        result = dict(dist)
        if not ranked or len(ranked) < 2:
            return result

        primary = ranked[0][0]
        pri_out = self._score_outcome(primary)
        home_fav = pri_out == "win" and (inp.win_rate >= 54.0 or (inp.sp_win is not None and inp.sp_win < 1.68))
        away_fav = pri_out == "lose" and (inp.lose_rate >= 54.0 or (inp.sp_lose is not None and inp.sp_lose < 1.68))

        if not home_fav and not away_fav:
            return result

        # Boost same-outcome alternates within odds gap (2:0 → 2:1/3:1)
        for score, odd in ranked[1:12]:
            if score == primary:
                continue
            if self._score_outcome(score) != pri_out:
                continue
            pri_odd = cmap.get(primary, 99)
            if odd - pri_odd <= 5.0:
                result[score] += result.get(score, 0) * 0.25
                break

        return result

    # ── Helpers (delegating to score_pick utilities) ─────────────────────

    @staticmethod
    def _rank_crs(score_odds: dict, skip: set[str]) -> list[tuple[str, float]]:
        from service.score_pick import _rank_crs
        return _rank_crs(score_odds, skip)

    @staticmethod
    def _best_draw(ranked: list[tuple[str, float]], skip: set[str]) -> str | None:
        from service.score_pick import _best_draw
        return _best_draw(ranked, skip)

    @staticmethod
    def _best_home_win(ranked, skip, expected_a: float = 1.0) -> str | None:
        from service.score_pick import _best_home_win
        return _best_home_win(ranked, skip, expected_a=expected_a)

    @staticmethod
    def _draw_close(primary: str, draw_pick: str, ranked, *,
                    ratio_cap: float = 1.55, gap_cap: float = 2.0) -> bool:
        from service.score_pick import _draw_close_to_primary
        return _draw_close_to_primary(ranked, primary, draw_pick,
                                       ratio_cap=ratio_cap, gap_cap=gap_cap)

    @staticmethod
    def _home_win_close_to_draw(draw_pick: str, home_win: str, ranked) -> bool:
        from service.score_pick import _home_win_close_to_draw
        return _home_win_close_to_draw(ranked, draw_pick, home_win)

    @staticmethod
    def _is_heavy_fav_away(lose_rate: float, sp_lose: float | None) -> bool:
        from service.score_pick_config import is_heavy_fav_away
        return is_heavy_fav_away(lose_rate, sp_lose)

    @staticmethod
    def _is_heavy_fav_home(win_rate: float, sp_win: float | None) -> bool:
        from service.score_pick_config import is_heavy_fav_home
        return is_heavy_fav_home(win_rate, sp_win)

    @staticmethod
    def _is_competitive(win_rate: float, lose_rate: float) -> bool:
        from service.score_pick_config import get_config
        cfg = get_config()
        gap = float(cfg.get("COMPETITIVE_WIN_GAP", 28.0))
        dr_min = float(cfg.get("COMPETITIVE_DRAW_MIN", 18.0))
        return abs(win_rate - lose_rate) < gap

    @staticmethod
    def _should_promote_draw(primary: str, draw_pick: str, ranked, inp: ScorerInput) -> bool:
        from service.score_pick_config import get_config
        cfg = get_config()
        hf_sp_win = float(cfg.get("HEAVY_FAV_SP_WIN", 1.55))
        ds_cap = float(cfg.get("DRAW_SP_CAP", 3.7))
        if inp.sp_win is not None and inp.sp_win < hf_sp_win:
            return False
        if inp.sp_draw is not None and inp.sp_draw > ds_cap:
            return False
        if inp.draw_rate < 26.0:
            return False
        cmap = dict(ranked)
        if cmap.get(primary) == cmap.get(draw_pick):
            return False
        return MarketCRSScorer._draw_close(primary, draw_pick, ranked)

    @staticmethod
    def _is_low_scoring_win_cluster(ranked, sp_draw: float | None = None) -> bool:
        from service.score_pick import _is_low_scoring_win_cluster
        return _is_low_scoring_win_cluster(ranked, sp_draw=sp_draw)

    @staticmethod
    def _market_fav_a(sp_win, sp_lose) -> bool | None:
        from service.score_pick import _market_fav_a
        return _market_fav_a(sp_win, sp_lose)

    @staticmethod
    def _best_margin_win(ranked, fav_a: bool, inp: ScorerInput, *, skip: set[str]) -> str | None:
        from service.score_pick import _best_margin_win
        return _best_margin_win(ranked, fav_a, inp.expected_a, inp.expected_b, skip=skip)

    def _normalize(self, dist: dict[str, float]) -> dict[str, float]:
        if not dist:
            return {}
        max_w = max(dist.values())
        if max_w <= 0:
            return {}
        return {s: w / max_w for s, w in dist.items()}

    def _compute_confidence(self, inp: ScorerInput) -> float:
        """Confidence depends on CRS data quality."""
        if not inp.score_odds:
            return 0.0
        # More scores in CRS pool = higher confidence
        n_scores = len([k for k in inp.score_odds if ":" in str(k)])
        return round(min(0.9, 0.4 + n_scores * 0.02), 2)
