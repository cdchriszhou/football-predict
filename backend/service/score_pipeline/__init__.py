"""
Score Pipeline — Poisson-first weighted ensemble for score prediction.

Public API:
    ScorePredictionPipeline  — main orchestrator
"""
from .pipeline import ScorePredictionPipeline
from .base import ScorerInput, ScorerResult, AggregatedScore, BaseScorer

__all__ = [
    "ScorePredictionPipeline",
    "ScorerInput",
    "ScorerResult",
    "AggregatedScore",
    "BaseScorer",
]
