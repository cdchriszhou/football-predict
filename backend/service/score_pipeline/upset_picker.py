"""
UpsetPicker — picks cold score from uncovered W/D/L direction.

Reuses existing pick_upset_from_crs() from score_pick.py, augmented with
weighted-aggregator tiebreaking when multiple upset candidates exist.
"""
from __future__ import annotations

from typing import Optional

from .base import AggregatedScore, ScorerInput


class UpsetPicker:
    """
    Picks best upset (cold score) from an uncovered W/D/L direction.

    Delegates to the battle-tested pick_upset_from_crs() for domain logic,
    using weighted-aggregator ranking as tiebreaker.
    """

    @staticmethod
    def _score_outcome(score: str) -> str:
        try:
            ga, gb = map(int, score.split(":"))
        except (ValueError, AttributeError):
            return "draw"
        if ga > gb:
            return "win"
        if ga < gb:
            return "lose"
        return "draw"

    def pick(
        self,
        aggregated: list[AggregatedScore],
        top_scores: list[str],
        crs: dict[str, float],
        inp: ScorerInput,
    ) -> Optional[str]:
        """
        Pick upset score from uncovered direction.

        Strategy:
        1. Use existing pick_upset_from_crs() for domain rule selection
        2. When multiple candidates, prefer higher aggregated weight
        3. Fall back to weighted aggregator if domain rules return nothing
        """
        from service.score_pick import pick_upset_from_crs

        # 1. Domain rules first (battle-tested logic)
        domain_upset = pick_upset_from_crs(
            crs, top_scores,
            win_rate=inp.win_rate,
            lose_rate=inp.lose_rate,
            draw_rate=inp.draw_rate,
            sp_win=inp.sp_win,
            sp_lose=inp.sp_lose,
            sp_draw=inp.sp_draw,
            handicap=inp.handicap,
            rank_a=inp.rank_a,
            rank_b=inp.rank_b,
            group_context=inp.group_context,
            team_a=inp.team_a,
            team_b=inp.team_b,
            odds_dict=inp.odds_dict,
        )

        if domain_upset and domain_upset not in ("胜其它", "平其它", "负其它", "?"):
            return domain_upset

        # 2. Fallback: use aggregator ranking for uncovered direction
        covered_outcomes = {self._score_outcome(s) for s in top_scores if s and s != "?"}
        for ascore in aggregated:
            if ascore.score in top_scores:
                continue
            outcome = self._score_outcome(ascore.score)
            if outcome not in covered_outcomes:
                # Check odds plausibility
                odd = crs.get(ascore.score, 99)
                if odd <= 25.0:
                    return ascore.score

        return domain_upset if domain_upset and domain_upset != "?" else None
