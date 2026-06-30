"""
ScoreValidator — post-processing validation of top-N aggregated scores.

Reuses existing well-tested validation functions from score_pick.py.
"""
from __future__ import annotations

from typing import Optional


class ScoreValidator:
    """
    Validates top-N aggregated picks: direction coverage, odd cap checks,
    upset plausibility, opposite-outcome pairs.
    """

    def validate(
        self,
        top_scores: list[str],
        upset: Optional[str],
        crs: dict[str, float],
        *,
        model_scores: Optional[list[str]] = None,
        win_rate: float = 50.0,
        draw_rate: float = 25.0,
        lose_rate: float = 50.0,
    ) -> tuple[list[str], Optional[str], list[str]]:
        """
        Returns (fixed_picks[:2], fixed_upset, warnings).

        Delegates to existing score_pick functions that are battle-tested.
        """
        from service.score_pick import (
            validate_score_picks,
            ensure_triple_direction_coverage,
            reconcile_likely_upset_cluster,
            _fix_opposite_outcome_likely_pair,
        )

        # 1. Fix opposite-outcome pairs (can't have 2:1 + 1:2)
        top_scores = _fix_opposite_outcome_likely_pair(
            top_scores, crs,
            win_rate=win_rate, draw_rate=draw_rate, lose_rate=lose_rate,
        )

        # 2. Fix upset cluster mislabeling
        top_scores, upset = reconcile_likely_upset_cluster(top_scores, upset, crs)

        # 3. Ensure direction coverage
        top_scores, upset = ensure_triple_direction_coverage(
            top_scores, upset, crs, model_scores,
        )

        # 4. Full validation
        top_scores, upset, warnings = validate_score_picks(
            top_scores, upset, crs,
            model_scores=model_scores,
            apply_ensure_triple=True,
            win_rate=win_rate, draw_rate=draw_rate, lose_rate=lose_rate,
        )

        return top_scores, upset, warnings
