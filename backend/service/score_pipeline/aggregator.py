"""
ScoreAggregator — weighted ensemble merge and ranking.

Combines all ScorerResult outputs into a single ranked list via weighted sum.
Each scorer's weight is configurable; the default is Poisson-dominant (0.50).
"""
from __future__ import annotations

from typing import Optional

from .base import AggregatedScore, ScorerResult


class ScoreAggregator:
    """
    Weighted ensemble: combines ScorerResult outputs into a ranked list.

    For each score line, sums (scorer_weight × score_weight) across all scorers.
    Ranks by total weight descending.
    """

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or self._default_weights()

    @staticmethod
    def _default_weights() -> dict[str, float]:
        from service.score_pick_config import get_config
        cfg = get_config()
        return {
            "poisson": float(cfg.get("POISSON_SCORER_WEIGHT", 0.50)),
            "market_crs": float(cfg.get("MARKET_CRS_SCORER_WEIGHT", 0.30)),
            "context": float(cfg.get("CONTEXT_SCORER_WEIGHT", 0.15)),
            "resilience": float(cfg.get("RESILIENCE_SCORER_WEIGHT", 0.05)),
            "knockout": float(cfg.get("KNOCKOUT_SCORER_WEIGHT", 0.10)),
        }

    def aggregate(self, scorer_results: list[ScorerResult]) -> list[AggregatedScore]:
        """
        Merge all scorer outputs into a single ranked list.

        1. For each scorer, multiply its score weights by its ensemble weight
        2. Sum across all scorers for each score line
        3. Rank by total weight descending
        """
        combined: dict[str, dict[str, float]] = {}  # score → {source → weighted_value}

        for result in scorer_results:
            if not result.scores:
                continue
            w = self.weights.get(result.source, 0.05)
            for score, value in result.scores.items():
                if score not in combined:
                    combined[score] = {}
                combined[score][result.source] = value * w

        min_weight = self._min_weight()
        aggregated = []
        for score, contribs in combined.items():
            total = sum(contribs.values())
            if total >= min_weight:
                aggregated.append(AggregatedScore(
                    score=score,
                    total_weight=total,
                    contributions=dict(contribs),
                ))

        aggregated.sort(key=lambda x: x.total_weight, reverse=True)
        return aggregated

    def top_scores(self, aggregated: list[AggregatedScore], n: int = 2) -> list[str]:
        """Return top-N score strings from aggregated ranking."""
        return [a.score for a in aggregated[:n]]

    def _min_weight(self) -> float:
        from service.score_pick_config import get_config
        cfg = get_config()
        return float(cfg.get("AGGREGATOR_MIN_WEIGHT", 0.001))
