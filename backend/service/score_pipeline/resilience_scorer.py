"""
ResilienceAdjustmentScorer — QUATERNARY scorer (default weight 0.05).

Fine-tunes for defensive/drought signals that indicate favourites stalling.
Detects patterns like opponent clean sheets, favourite scoring droughts,
defensive tactics, and group-wide low scoring.
"""
from __future__ import annotations

from typing import Optional

from .base import BaseScorer, ScorerInput, ScorerResult


class ResilienceAdjustmentScorer(BaseScorer):
    """QUATERNARY scorer for defensive/drought resilience signals."""

    label = "resilience"

    def score(self, inp: ScorerInput) -> ScorerResult:
        from service.score_context import detect_resilience_signals

        signals = detect_resilience_signals(
            inp.group_context, inp.odds_dict,
            inp.rank_a, inp.rank_b,
            team_a=inp.team_a or {}, team_b=inp.team_b or {},
        )

        if signals.get("matchday", 0) < 2:
            return ScorerResult(scores={}, confidence=1.0, rationale="R1 no resilience", source=self.label)

        adjustments: dict[str, float] = {}

        # Boost conservative scores, demote rout lines
        if signals.get("opponent_clean_sheet") or signals.get("favorite_scoring_drought"):
            adjustments = self._boost_conservative(adjustments, inp, signals)
        if signals.get("opponent_defensive") and signals.get("group_low_scoring"):
            adjustments = self._suppress_blowout(adjustments, inp, signals)

        return ScorerResult(
            scores=adjustments,
            confidence=0.6 if adjustments else 1.0,
            rationale=self._build_rationale(signals),
            source=self.label,
        )

    def _boost_conservative(
        self, adj: dict[str, float], inp: ScorerInput, signals: dict,
    ) -> dict[str, float]:
        """Promote draw and narrow-margin scores."""
        result = dict(adj)
        # Boost draw lines
        for s in ("1:1", "0:0", "2:2"):
            if s in inp.score_odds:
                result[s] = result.get(s, 0) + 0.10

        # Demote rout lines
        if signals.get("fav_a") and signals.get("opponent_clean_sheet"):
            for s in ("4:0", "5:0", "6:0", "3:0", "4:1"):
                if s in inp.score_odds:
                    result[s] = result.get(s, 0) - 0.15
        elif not signals.get("fav_a") and signals.get("opponent_clean_sheet"):
            for s in ("0:4", "0:5", "0:6", "0:3", "1:4"):
                if s in inp.score_odds:
                    result[s] = result.get(s, 0) - 0.15

        return result

    def _suppress_blowout(
        self, adj: dict[str, float], inp: ScorerInput, signals: dict,
    ) -> dict[str, float]:
        """Suppress high-margin scorelines when group is low-scoring."""
        result = dict(adj)
        for s in inp.score_odds:
            try:
                ga, gb = map(int, s.split(":"))
            except ValueError:
                continue
            if abs(ga - gb) >= 3:
                result[s] = result.get(s, 0) - 0.12
        return result

    def _build_rationale(self, signals: dict) -> str:
        parts = []
        if signals.get("opponent_clean_sheet"):
            parts.append("opponent clean sheet")
        if signals.get("favorite_scoring_drought"):
            parts.append("fav scoring drought")
        if signals.get("opponent_defensive"):
            parts.append("defensive opponent")
        return ", ".join(parts) if parts else ""
