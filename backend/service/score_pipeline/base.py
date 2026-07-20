"""
Score Pipeline Base — core abstractions for the weighted ensemble architecture.

Each Scorer independently evaluates a match and returns a dict of score→weight.
The Aggregator merges all scorer outputs via weighted sum to produce a final ranking.
This replaces the 20-step sequential override pipeline with a composable ensemble.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScorerInput:
    """Unified input for all scorers — every scorer sees the same data."""

    score_odds: dict[str, float]  # CRS market odds {"1:0": 5.3, ...}
    win_rate: float
    draw_rate: float
    lose_rate: float
    expected_a: float = 1.2  # xG for team A
    expected_b: float = 1.0  # xG for team B
    sp_win: Optional[float] = None  # Euro SPF home win odds
    sp_draw: Optional[float] = None
    sp_lose: Optional[float] = None
    handicap: Optional[str] = None  # Asian handicap line
    rank_a: Optional[int] = None
    rank_b: Optional[int] = None
    group_context: Optional[dict] = None
    odds_dict: Optional[dict] = None  # Full fused odds dict
    team_a: Optional[dict] = None
    team_b: Optional[dict] = None
    stage: Optional[str] = None
    model_scores: Optional[list[str]] = None  # Poisson model hints
    rule_result: Optional[object] = None  # RulePrediction


@dataclass
class ScorerResult:
    """Each scorer returns a weight dict with metadata for traceability."""

    scores: dict[str, float]  # score → weight (positive=promote, negative=demote)
    confidence: float = 1.0  # 0.0–1.0 how applicable this scorer is
    rationale: str = ""  # human-readable explanation
    source: str = "base"  # label for traceability


@dataclass
class AggregatedScore:
    """A single scoreline after weighted aggregation with traceable contributions."""

    score: str
    total_weight: float
    contributions: dict[str, float] = field(default_factory=dict)  # source → weight


class BaseScorer(ABC):
    """
    Abstract scorer. Each scorer is independent and composable.

    Instead of overriding previous decisions (old pattern), each scorer
    contributes additive weights to a shared pool. The Aggregator then
    sums weights across all scorers to produce the final ranking.
    """

    label: str = "base"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def score(self, inp: ScorerInput) -> ScorerResult:
        """Produce score → weight mapping from this scorer's perspective."""
        ...

    @staticmethod
    def _describe(*parts: str) -> str:
        return "; ".join(p for p in parts if p)

    @staticmethod
    def _parse_handicap(handicap: str | None) -> float:
        if not handicap:
            return 0.0
        try:
            return float(str(handicap).replace("+", ""))
        except (TypeError, ValueError):
            return 0.0

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
