"""
PoissonModelScorer — PRIMARY scorer (default weight 0.50).

Uses Dixon-Coles Poisson expected-goals model as the foundation for score
predictions. Applies model-internal adjustments (rout boost, blowout tiers,
strong-home promotion, open-game high scores, narrow-home-win, extreme
favourite shutouts) as ADDITIVE weight contributions — never as destructive
overrides.
"""
from __future__ import annotations

import math
from typing import Optional

from .base import BaseScorer, ScorerInput, ScorerResult


class PoissonModelScorer(BaseScorer):
    """
    PRIMARY scorer. Dixon-Coles Poisson distribution with model-internal
    adjustments for rout potential, home advantage, and tactical patterns.

    All adjustments are additive — they boost or dampen scores in the
    distribution rather than replacing the top pick.
    """

    label = "poisson"

    # ── Constants ────────────────────────────────────────────────────────
    MAX_GOALS = 8
    DIXON_COLES_RHO = -0.13
    AVG_GOALS = 2.75
    MAX_XG_PER_TEAM = 5.5

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.DIXON_COLES_RHO = float(config.get("dixon_coles_rho", -0.13)) if config else -0.13
        self.AVG_GOALS = float(config.get("avg_goals", 2.75)) if config else 2.75

    # ── Public API ──────────────────────────────────────────────────────

    def score(self, inp: ScorerInput) -> ScorerResult:
        if not inp.score_odds:
            return ScorerResult(scores={}, confidence=0.0, rationale="no CRS pool", source=self.label)

        # 1. Compute base Dixon-Coles Poisson distribution
        dist = self._compute_poisson_dist(inp)

        # 2. Apply model-internal adjustments (additive weight boosts)
        dist = self._apply_favourite_shutout_bias(dist, inp)
        dist = self._apply_rout_boost(dist, inp)
        dist = self._apply_blowout_tiers(dist, inp)
        dist = self._apply_strong_home_multi_goal(dist, inp)
        dist = self._apply_open_game_high_score(dist, inp)
        dist = self._apply_extreme_home_fav(dist, inp)
        dist = self._apply_host_opener_blowout(dist, inp)

        # 3. Preserve the top draw score — ensure draws are not suppressed
        dist = self._preserve_top_draw(dist)

        # 4. Normalize to [0, 1] range
        normalized = self._normalize(dist)

        return ScorerResult(
            scores=normalized,
            confidence=self._compute_confidence(inp),
            rationale=f"Poisson xG {inp.expected_a:.1f}/{inp.expected_b:.1f}",
            source=self.label,
        )

    # ── Poisson Distribution ────────────────────────────────────────────

    def _compute_poisson_dist(self, inp: ScorerInput) -> dict[str, float]:
        """Compute full Dixon-Coles score probability distribution."""
        ex_a = inp.expected_a
        ex_b = inp.expected_b
        draw_rate = inp.draw_rate
        handicap = self._parse_handicap(inp.handicap)
        over_under = float((inp.odds_dict or {}).get("over_under", 2.5) or 2.5)

        # Poisson PMF for each team
        def poisson_pmf(lmbda: float) -> dict[int, float]:
            if lmbda <= 0:
                return {0: 1.0}
            probs = {}
            for k in range(self.MAX_GOALS + 1):
                probs[k] = (lmbda ** k) * math.exp(-lmbda) / math.factorial(k)
            tail = max(0.0, 1.0 - sum(probs.values()))
            probs[self.MAX_GOALS] += tail
            return probs

        pa = poisson_pmf(ex_a)
        pb = poisson_pmf(ex_b)
        draw_boost = 1.0 + (draw_rate / 100.0) * 0.45

        dist: dict[str, float] = {}
        for ga in range(self.MAX_GOALS + 1):
            for gb in range(self.MAX_GOALS + 1):
                prob = pa.get(ga, 0) * pb.get(gb, 0)
                # Dixon-Coles low-score correlation
                prob *= self._dc_tau(ga, gb, ex_a, ex_b)

                if ga == gb:
                    prob *= draw_boost

                # Handicap alignment
                if handicap != 0.0:
                    margin = ga - gb
                    target_margin = handicap if handicap > 0 else -abs(handicap)
                    margin_diff = abs(margin - target_margin)
                    if margin_diff < 0.5:
                        prob *= 1.15
                    elif margin_diff < 1.0:
                        prob *= 1.08

                total = ga + gb
                # Relaxed penalty factors (was 0.45/0.65 — too aggressive)
                if total > 7:
                    prob *= 0.65
                elif total > 5:
                    prob *= 0.80

                if abs(margin := ga - gb) >= 5:
                    prob *= 0.65

                # Over/under alignment
                if over_under <= 2.5 and total >= 4:
                    prob *= 0.70
                elif over_under >= 3.0 and total <= 2:
                    prob *= 0.75

                dist[f"{ga}:{gb}"] = prob

        return dist

    def _dc_tau(self, ga: int, gb: int, la: float, lb: float) -> float:
        """Dixon-Coles low-score correlation adjustment."""
        rho = self.DIXON_COLES_RHO
        if ga == 0 and gb == 0:
            return 1.0 - la * lb * rho
        if ga == 0 and gb == 1:
            return 1.0 + la * rho
        if ga == 1 and gb == 0:
            return 1.0 + lb * rho
        if ga == 1 and gb == 1:
            return 1.0 - rho
        return 1.0

    # ── Model-Internal Adjustments (additive weights) ────────────────────

    def _apply_favourite_shutout_bias(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """Favourite clean-sheet bias: mild boost to shutout wins, mild dampen of draws.

        Uses gentler factors (1.18/0.85 vs old 1.35/0.72) to preserve Poisson model's
        natural draw probability — the old aggressive factors were suppressing draws
        too heavily, causing the system to almost never predict draws.
        """
        margin = inp.expected_a - inp.expected_b
        result = dict(dist)
        if margin >= 0.85:
            for s, p in dist.items():
                try:
                    ga, gb = map(int, s.split(":"))
                except ValueError:
                    continue
                if ga > gb and gb == 0:
                    result[s] = p * 1.18
                elif ga == gb:
                    result[s] = p * 0.85
        elif margin <= -0.85:
            for s, p in dist.items():
                try:
                    ga, gb = map(int, s.split(":"))
                except ValueError:
                    continue
                if gb > ga and ga == 0:
                    result[s] = p * 1.18
                elif ga == gb:
                    result[s] = p * 0.85
        return result

    def _apply_rout_boost(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """Boost high-margin win scores for clear favourites — strong enough to flip rankings."""
        rank_gap = abs(int(inp.rank_a or 50) - int(inp.rank_b or 50))
        hcp = self._parse_handicap(inp.handicap)

        # Determine favourite side and strength
        is_home_fav = inp.win_rate >= inp.lose_rate
        sp_fav = inp.sp_win if is_home_fav else inp.sp_lose
        fav_rate = inp.win_rate if is_home_fav else inp.lose_rate

        # Only boost when there's a clear favourite
        if fav_rate < 55.0 and sp_fav is None:
            return dist
        if sp_fav is not None and sp_fav >= 1.80:
            return dist
        if rank_gap < 20 and sp_fav is not None and sp_fav >= 1.55:
            return dist

        result = dict(dist)
        # Rout boost — moderate to avoid over-suppressing draws
        boost = 1.2
        if sp_fav is not None:
            if sp_fav < 1.25:
                boost = 2.0
            elif sp_fav < 1.35:
                boost = 1.7
            elif sp_fav < 1.50:
                boost = 1.4
            elif sp_fav < 1.65:
                boost = 1.2

        # Apply to rout scores (3+ goal margin, conceding ≤1)
        for s in list(result.keys()):
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            if is_home_fav and ga > gb and ga >= 3 and gb <= 1:
                result[s] += result[s] * boost
            elif not is_home_fav and gb > ga and gb >= 3 and ga <= 1:
                result[s] += result[s] * boost
        return result

    def _apply_blowout_tiers(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """Shutout-first tiers for deep-favourite rout promotion (4:0, 3:0, 5:0...)."""
        from service.score_pick_config import get_config
        cfg = get_config()
        tiers = cfg.get("BLOWOUT_TIERS", [
            ("4:0", 1.75, 1.35), ("3:0", 1.50, 1.55), ("5:0", 2.00, 1.25),
            ("6:0", 2.50, 1.18), ("7:0", 3.00, 1.15), ("4:1", 1.85, 1.55),
            ("3:1", 1.65, 1.50), ("6:1", 2.80, 1.20), ("7:1", 3.20, 1.18),
        ])
        away_tiers = cfg.get("BLOWOUT_TIERS_AWAY", [
            ("0:4", 1.75, 1.35), ("0:3", 1.50, 1.55), ("0:5", 2.00, 1.25),
            ("1:4", 1.85, 1.55), ("1:3", 1.65, 1.50),
        ])

        hcp = self._parse_handicap(inp.handicap)
        result = dict(dist)

        # Home favourite blowout
        if inp.win_rate >= 48.0 and inp.sp_win is not None and inp.sp_win < 1.90:
            if not (hcp > -0.5 and inp.sp_win >= 1.80):
                for score, min_xg, max_sp in tiers:
                    if score not in result:
                        continue
                    eff_max = max_sp
                    if score in ("4:0", "5:0") and inp.expected_a >= 2.0:
                        eff_max = max(eff_max, 1.82)
                    if inp.sp_win >= eff_max:
                        continue
                    if inp.expected_a < min_xg:
                        continue
                    boost = (1.0 - inp.sp_win / max(eff_max * 2, 1.0)) * 2.5
                    result[score] += result.get(score, 0) * max(0.15, boost)

        # Away favourite blowout
        if inp.lose_rate >= 48.0 and inp.sp_lose is not None and inp.sp_lose < 1.90:
            if not (hcp < 0.5 and inp.sp_lose >= 1.80):
                for score, min_xg, max_sp in away_tiers:
                    if score not in result:
                        continue
                    eff_max = max_sp
                    if score in ("0:4", "0:5") and inp.expected_b >= 2.0:
                        eff_max = max(eff_max, 1.82)
                    if inp.sp_lose >= eff_max:
                        continue
                    if inp.expected_b < min_xg:
                        continue
                    boost = (1.0 - inp.sp_lose / max(eff_max * 2, 1.0)) * 2.5
                    result[score] += result.get(score, 0) * max(0.15, boost)
        return result

    def _apply_strong_home_multi_goal(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """SPF home fav <1.70: boost 2:0/2:1/3:0 over 1:0."""
        if inp.win_rate < 48.0 or inp.sp_win is None or inp.sp_win >= 1.70:
            return dist

        result = dict(dist)
        candidates = ("3:0", "2:0", "2:1") if inp.sp_win < 1.45 and inp.win_rate >= 58.0 else ("2:0", "2:1", "3:0")
        for score in candidates:
            if score in result and result[score] > 0:
                result[score] *= 1.18
        return result

    def _apply_open_game_high_score(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """High xG, both sides can score: boost 3:2/4:2-style scores."""
        total_xg = inp.expected_a + inp.expected_b
        if total_xg < 3.8:
            return dist
        spread = abs(inp.win_rate - inp.lose_rate)

        result = dict(dist)
        for s in result:
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            if ga + gb >= 3 and ga >= 1 and gb >= 1 and ga != gb:
                boost = 1.18
                if ga + gb >= 4:
                    boost = 1.35
                if total_xg >= 4.4:
                    boost *= 1.15
                result[s] *= boost
        return result

    def _apply_extreme_home_fav(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """Ultra-deep favourite (home or away): boost 5:0/6:0 / 0:5/0:6 lines."""
        hcp = self._parse_handicap(inp.handicap)
        result = dict(dist)

        # Home extreme fav
        if inp.win_rate >= 68.0 and inp.sp_win is not None and inp.sp_win < 1.30 and hcp <= -1.5:
            for s in result:
                try:
                    ga, gb = map(int, s.split(":"))
                except ValueError:
                    continue
                if ga >= 4 and gb == 0:
                    result[s] *= 1.35

        # Away extreme fav
        if inp.lose_rate >= 68.0 and inp.sp_lose is not None and inp.sp_lose < 1.30 and hcp >= 1.5:
            for s in result:
                try:
                    ga, gb = map(int, s.split(":"))
                except ValueError:
                    continue
                if gb >= 4 and ga == 0:
                    result[s] *= 1.35
        return result

    def _apply_host_opener_blowout(self, dist: dict[str, float], inp: ScorerInput) -> dict[str, float]:
        """Host nation opener + clear favourite: boost home rout scores (4:1, 3:1)."""
        ctx = inp.group_context or {}
        if not ctx.get("is_group_opener") or not ctx.get("home_side"):
            return dist
        if inp.win_rate < 48.0:
            return dist
        if inp.expected_a < 1.95:
            return dist

        result = dict(dist)
        for s in ("4:1", "3:1", "4:0", "3:0"):
            if s in result:
                result[s] *= 1.22
        return result

    def _preserve_top_draw(self, dist: dict[str, float]) -> dict[str, float]:
        """Ensure the top draw score is not suppressed below 85% of the top overall score.

        This prevents the shutout bias from completely eliminating draws from
        consideration, which was causing the system to predict draws only 2% of the time
        vs the actual 28% draw rate in the 2026 World Cup.
        """
        if not dist:
            return dist
        result = dict(dist)

        # Find top overall score
        top_score = max(result, key=result.get)
        top_weight = result[top_score]

        # Find top draw score
        top_draw = None
        top_draw_weight = 0.0
        for s, w in result.items():
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            if ga == gb and w > top_draw_weight:
                top_draw = s
                top_draw_weight = w

        # Ensure top draw gets at least 85% of top overall weight
        if top_draw and top_weight > 0 and top_draw_weight < top_weight * 0.85:
            result[top_draw] = top_weight * 0.85

        return result

    # ── Helpers ─────────────────────────────────────────────────────────

    def _normalize(self, dist: dict[str, float]) -> dict[str, float]:
        """Normalize weight distribution to [0, 1] range."""
        if not dist:
            return {}
        max_w = max(dist.values())
        if max_w <= 0:
            return {}
        return {s: w / max_w for s, w in dist.items()}

    def _compute_confidence(self, inp: ScorerInput) -> float:
        """Higher confidence when xG and rank gap are clear."""
        gap = abs(inp.expected_a - inp.expected_b)
        rank_gap = abs(int(inp.rank_a or 50) - int(inp.rank_b or 50))
        conf = 0.5 + min(0.4, gap * 0.15 + rank_gap / 200)
        return round(min(1.0, conf), 2)
