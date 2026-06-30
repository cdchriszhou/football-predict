"""
KnockoutMarketScorer — knockout-stage专用评分器 (default weight 0.10).

Integrates European 1X2 + Asian handicap + Over/Under + Half/Full odds
into score prediction for knockout-stage matches. Returns empty results
for group-stage matches (stage-gated).

Six signals, all additive weights:
  1. Handicap → xG margin alignment
  2. Over/Under → total goals constraint
  3. Half/Full consistency check
  4. Extra time probability estimation
  5. Knockout draw protection signal
  6. Shallow handicap trap detection
"""
from __future__ import annotations

from typing import Optional

from .base import BaseScorer, ScorerInput, ScorerResult


class KnockoutMarketScorer(BaseScorer):
    """Knockout-specific scorer using European + Asian handicap data."""

    label = "knockout"

    def score(self, inp: ScorerInput) -> ScorerResult:
        stage = inp.stage or ""
        ctx = inp.group_context or {}
        actual_stage = ctx.get("stage", stage)

        # Stage-gate: only activate for knockout matches
        if not actual_stage or actual_stage in ("", "小组赛"):
            return ScorerResult(scores={}, confidence=1.0, rationale="group stage skip", source=self.label)

        adjustments: dict[str, float] = {}

        # ── Signal 1: Handicap → xG margin ──
        adjustments = self._apply_handicap_margin(adjustments, inp)

        # ── Signal 2: Over/Under → total goals ──
        adjustments = self._apply_over_under_constraint(adjustments, inp)

        # ── Signal 3: Half/Full consistency ──
        adjustments = self._apply_half_full_consistency(adjustments, inp)

        # ── Signal 4: Extra time probability ──
        et_prob = self._compute_et_probability(inp, actual_stage)
        adjustments = self._apply_et_adjustment(adjustments, inp, et_prob)

        # ── Signal 5: Draw protection (knockout-specific) ──
        adjustments = self._apply_ko_draw_protection(adjustments, inp)

        # ── Signal 6: Shallow handicap trap ──
        adjustments = self._apply_shallow_trap(adjustments, inp)

        return ScorerResult(
            scores=adjustments,
            confidence=0.65,
            rationale=self._build_rationale(actual_stage, et_prob),
            source=self.label,
        )

    # ── Signal 1: Handicap → xG Margin ──────────────────────────────────

    def _apply_handicap_margin(
        self, adj: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """Boost scores matching the handicap-implied goal margin."""
        result = dict(adj)
        handicap = inp.handicap
        if not handicap or not inp.score_odds:
            return result

        from service.handicap_xg import handicap_to_score_weights
        hcp = self._parse_handicap(handicap)
        if hcp == 0:
            return result

        hw_odds = (inp.odds_dict or {}).get("handicap_win")
        hl_odds = (inp.odds_dict or {}).get("handicap_lose")

        weights = handicap_to_score_weights(
            hcp, hw_odds, hl_odds,
            inp.score_odds,
            inp.win_rate, inp.lose_rate,
        )
        for s, w in weights.items():
            result[s] = result.get(s, 0) + w
        return result

    # ── Signal 2: Over/Under → Total Goals ──────────────────────────────

    def _apply_over_under_constraint(
        self, adj: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """Boost scores matching the O/U-implied total goals."""
        result = dict(adj)
        ou_raw = (inp.odds_dict or {}).get("over_under")
        if not ou_raw or not inp.score_odds:
            return result

        try:
            ou_line = float(ou_raw)
        except (TypeError, ValueError):
            return result

        from service.handicap_xg import over_under_to_score_weights
        over_odds = (inp.odds_dict or {}).get("over_odds")
        under_odds = (inp.odds_dict or {}).get("under_odds")

        weights = over_under_to_score_weights(
            ou_line, over_odds, under_odds, inp.score_odds,
        )
        for s, w in weights.items():
            result[s] = result.get(s, 0) + w
        return result

    # ── Signal 3: Half/Full Consistency ──────────────────────────────────

    def _apply_half_full_consistency(
        self, adj: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """
        Check if half/full odds direction matches CRS direction.
        When they disagree, reduce confidence in extreme scorelines.
        """
        result = dict(adj)
        hf_odds = (inp.odds_dict or {}).get("half_full_odds", {})
        if not hf_odds or not isinstance(hf_odds, dict):
            return result

        # Determine half/full favourite direction
        hf_fav = self._hf_favourite_direction(hf_odds)
        if hf_fav is None:
            return result

        # Determine CRS favourite direction
        crs_fav = self._crs_favourite_direction(inp.score_odds)
        if crs_fav is None:
            return result

        # Consistency check
        if hf_fav == crs_fav:
            # Consistent: slight boost to favourite-side scores
            for s in inp.score_odds:
                if ":" not in str(s):
                    continue
                try:
                    ga, gb = map(int, s.split(":"))
                except ValueError:
                    continue
                if (crs_fav == "home" and ga > gb) or (crs_fav == "away" and gb > ga):
                    result[s] = result.get(s, 0) + 0.05
        else:
            # Inconsistent: market uncertain, boost draw/narrow margins
            for s in inp.score_odds:
                if ":" not in str(s):
                    continue
                try:
                    ga, gb = map(int, s.split(":"))
                except ValueError:
                    continue
                margin = abs(ga - gb)
                if margin <= 1:
                    result[s] = result.get(s, 0) + 0.10

        return result

    @staticmethod
    def _hf_favourite_direction(hf_odds: dict) -> Optional[str]:
        """Determine which side half/full market favours."""
        home_signals = 0
        away_signals = 0
        # Check top entries in half/full odds
        sorted_hf = sorted(hf_odds.items(), key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else 99)
        for key, odd in sorted_hf[:3]:
            key_str = str(key)
            if "胜" in key_str and "负" not in key_str:
                home_signals += 1
            elif "负" in key_str:
                away_signals += 1
        if home_signals > away_signals:
            return "home"
        elif away_signals > home_signals:
            return "away"
        return None

    @staticmethod
    def _crs_favourite_direction(score_odds: dict) -> Optional[str]:
        """Determine which side CRS market favours."""
        home_wins = away_wins = 0
        sorted_crs = sorted(
            [(k, v) for k, v in score_odds.items() if ":" in str(k)],
            key=lambda x: float(x[1]),
        )[:5]
        for s, _ in sorted_crs:
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            if ga > gb:
                home_wins += 1
            elif gb > ga:
                away_wins += 1
        if home_wins > away_wins:
            return "home"
        elif away_wins > home_wins:
            return "away"
        return None

    # ── Signal 4: Extra Time Probability ─────────────────────────────────

    def _compute_et_probability(self, inp: ScorerInput, stage: str) -> float:
        """Estimate probability match goes to extra time."""
        from service.handicap_xg import estimate_et_probability
        rank_gap = abs(int(inp.rank_a or 50) - int(inp.rank_b or 50))
        draw_odds = inp.sp_draw or (inp.odds_dict or {}).get("draw")
        imp_draw = (inp.odds_dict or {}).get("imp_draw", inp.draw_rate)
        return estimate_et_probability(rank_gap, draw_odds, imp_draw, stage)

    def _apply_et_adjustment(
        self, adj: dict[str, float], inp: ScorerInput, et_prob: float,
    ) -> dict[str, float]:
        """
        When ET probability is high, boost draw scores and narrow margins.
        This reflects the reality that knockout matches are often tight.
        """
        result = dict(adj)
        if et_prob < 0.12:
            return result

        # Boost draw scores proportionally to ET probability
        boost = et_prob * 0.8
        for s in inp.score_odds:
            if ":" not in str(s):
                continue
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            # Boost draws strongly
            if ga == gb:
                result[s] = result.get(s, 0) + boost * 0.6
            # Boost narrow 1-goal margins moderately
            elif abs(ga - gb) == 1:
                result[s] = result.get(s, 0) + boost * 0.3
            # Demote blowouts
            elif abs(ga - gb) >= 3:
                result[s] = result.get(s, 0) - boost * 0.4

        return result

    # ── Signal 5: Knockout Draw Protection ──────────────────────────────

    def _apply_ko_draw_protection(
        self, adj: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """
        In knockout matches, bookmakers often protect the draw more aggressively.
        Low draw odds (<3.2) in knockout = strong draw signal.
        """
        result = dict(adj)
        draw_odds = inp.sp_draw or (inp.odds_dict or {}).get("draw")
        if not draw_odds or float(draw_odds) > 3.4:
            return result

        draw_odd = float(draw_odds)
        # Stronger signal for lower draw odds
        if draw_odd < 2.8:
            boost = 0.30
        elif draw_odd < 3.0:
            boost = 0.20
        elif draw_odd < 3.2:
            boost = 0.12
        else:
            boost = 0.06

        for s in inp.score_odds:
            if ":" not in str(s):
                continue
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            if ga == gb:
                result[s] = result.get(s, 0) + boost
            elif abs(ga - gb) == 1 and ga + gb <= 3:
                result[s] = result.get(s, 0) + boost * 0.5

        return result

    # ── Signal 6: Shallow Handicap Trap ──────────────────────────────────

    def _apply_shallow_trap(
        self, adj: dict[str, float], inp: ScorerInput,
    ) -> dict[str, float]:
        """
        Strong favourite with shallow handicap in knockout = trap.
        Bookmakers doubt the favourite will cover; reduce blowout weights.
        """
        result = dict(adj)
        handicap = inp.handicap
        sp_win = inp.sp_win
        sp_lose = inp.sp_lose

        if not handicap or not inp.score_odds:
            return result

        hcp = self._parse_handicap(handicap)
        fav_side = "home" if inp.win_rate >= inp.lose_rate else "away"

        # Detect shallow handicap trap
        is_trap = False
        if fav_side == "home" and sp_win and sp_win < 1.55 and hcp > -0.75:
            is_trap = True
        elif fav_side == "away" and sp_lose and sp_lose < 1.55 and hcp < 0.75:
            is_trap = True

        if not is_trap:
            return result

        # Reduce blowout weights, boost tight margins
        for s in inp.score_odds:
            if ":" not in str(s):
                continue
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            margin = abs(ga - gb)
            if margin >= 3:
                result[s] = result.get(s, 0) - 0.25
            elif margin <= 1:
                result[s] = result.get(s, 0) + 0.12

        return result

    # ── Helpers ─────────────────────────────────────────────────────────

    def _build_rationale(self, stage: str, et_prob: float) -> str:
        parts = [f"KO {stage}"]
        if et_prob >= 0.15:
            parts.append(f"ET prob {et_prob:.0%}")
        return "; ".join(parts)
