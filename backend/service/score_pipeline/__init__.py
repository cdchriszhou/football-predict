"""
Score Pipeline — Poisson-first weighted ensemble for score prediction.

Public API:
    ScorePredictionPipeline  — main orchestrator
    run_score_pipeline()     — convenience function (drop-in for old pipeline)

The pipeline replaces the 20-step sequential override chain with a 5-scorer
weighted ensemble. Each scorer adds weight to a shared pool; the Aggregator
ranks scores by total weight.

Scorer weights (configurable via score_pick_config.py):
    PoissonModelScorer     (0.50) — Dixon-Coles distribution
    MarketCRSScorer        (0.30) — CRS market odds
    ContextAdjustmentScorer(0.15) — group standings, motivation
    ResilienceAdjustmentScorer(0.05) — defensive/drought signals
    KnockoutMarketScorer   (0.10) — knockout: handicap, O/U, ET probability
"""
from .pipeline import ScorePredictionPipeline
from .base import ScorerInput, ScorerResult, AggregatedScore, BaseScorer
from .knockout_scorer import KnockoutMarketScorer

__all__ = [
    "ScorePredictionPipeline",
    "ScorerInput",
    "ScorerResult",
    "AggregatedScore",
    "BaseScorer",
    "KnockoutMarketScorer",
]
