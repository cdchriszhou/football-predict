"""
ScorePredictionPipeline — Poisson-first weighted ensemble orchestrator.

Replaces the 20-step sequential override pipeline with a 7-step ensemble:
  1. PoissonModelScorer    → base distribution from Dixon-Coles (HIGH weight)
  2. MarketCRSScorer       → CRS market odds validation (MEDIUM weight)
  3. ContextAdjustmentScorer → group standings, motivation (LOW weight)
  4. ResilienceAdjustmentScorer → defensive/drought signals (LOW weight)
  5. ScoreAggregator       → weighted sum → ranked score list
  6. ScoreValidator        → direction coverage, odd checks
  7. UpsetPicker           → cold score from uncovered direction

Key change from old pipeline: scorers ADD weight, never OVERRIDE.
"""
from __future__ import annotations

from typing import Optional

from .base import AggregatedScore, ScorerInput
from .poisson_scorer import PoissonModelScorer
from .market_crs_scorer import MarketCRSScorer
from .context_scorer import ContextAdjustmentScorer
from .resilience_scorer import ResilienceAdjustmentScorer
from .knockout_scorer import KnockoutMarketScorer
from .aggregator import ScoreAggregator
from .validator import ScoreValidator
from .upset_picker import UpsetPicker


class ScorePredictionPipeline:
    """
    Poisson-first weighted ensemble for World Cup score prediction.

    Same interface as old run_full_score_pipeline() for drop-in compatibility.
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.poisson_scorer = PoissonModelScorer(cfg.get("poisson"))
        self.market_scorer = MarketCRSScorer(cfg.get("market_crs"))
        self.context_scorer = ContextAdjustmentScorer(cfg.get("context"))
        self.resilience_scorer = ResilienceAdjustmentScorer(cfg.get("resilience"))
        self.knockout_scorer = KnockoutMarketScorer(cfg.get("knockout"))
        self.aggregator = ScoreAggregator(cfg.get("weights"))
        self.validator = ScoreValidator()
        self.upset_picker = UpsetPicker()

    def run(
        self,
        crs: dict[str, float],
        *,
        win_rate: float,
        draw_rate: float,
        lose_rate: float,
        expected_a: float = 1.2,
        expected_b: float = 1.0,
        model_scores: Optional[list[str]] = None,
        stage: Optional[str] = None,
        sp_win: Optional[float] = None,
        sp_lose: Optional[float] = None,
        sp_draw: Optional[float] = None,
        handicap: Optional[str] = None,
        rank_a: Optional[int] = None,
        rank_b: Optional[int] = None,
        group_context: Optional[dict] = None,
        odds_dict: Optional[dict] = None,
        rule_result=None,
        team_a: Optional[dict] = None,
        team_b: Optional[dict] = None,
        skip_wdl_resilience: bool = False,
    ) -> tuple[list[str], Optional[str], list[str], list[str]]:
        """
        Run the full weighted-ensemble score prediction pipeline.

        Returns (best_scores[:2], upset, all_picks, warnings).
        Same signature as old run_full_score_pipeline().
        """
        hints = [s for s in (model_scores or []) if s and s != "?"]
        if not crs:
            fallback = hints[:2] if hints else ["?"]
            return fallback, None, fallback, []

        # ── Pre-process: WDL adjustments ──
        adjusted_wr, adjusted_dr, adjusted_lr = self._preprocess_wdl(
            win_rate, draw_rate, lose_rate,
            group_context, odds_dict, rank_a, rank_b,
            team_a, team_b, sp_win, sp_lose, sp_draw, handicap,
            skip_wdl_resilience,
        )

        # Stage-based draw adjustment (skip MD3 must-win)
        ctx = group_context or {}
        if not (
            ctx.get("matchday") == 3
            and ctx.get("stage") == "小组赛"
            and (ctx.get("must_win_a") or ctx.get("must_win_b") or ctx.get("both_must_win"))
        ):
            from service.score_pick import apply_stage_draw_adjustment
            adjusted_wr, adjusted_dr, adjusted_lr = apply_stage_draw_adjustment(
                adjusted_wr, adjusted_dr, adjusted_lr, stage,
                sp_win=sp_win, sp_lose=sp_lose,
            )

        # ── Build unified input ──
        # Detect when CRS+handicap strongly disagree with WDL (e.g. Curacao +2)
        crs_orientation_bonus = self._detect_crs_handicap_orientation(
            crs, handicap, adjusted_wr, adjusted_dr, adjusted_lr,
        )

        inp = ScorerInput(
            score_odds=crs,
            win_rate=adjusted_wr,
            draw_rate=adjusted_dr,
            lose_rate=adjusted_lr,
            expected_a=expected_a,
            expected_b=expected_b,
            sp_win=sp_win, sp_draw=sp_draw, sp_lose=sp_lose,
            handicap=handicap,
            rank_a=rank_a, rank_b=rank_b,
            group_context=group_context,
            odds_dict=odds_dict,
            team_a=team_a, team_b=team_b,
            stage=stage,
            model_scores=hints or None,
            rule_result=rule_result,
        )

        # ── Weighted Ensemble (Steps 1-5) ──
        scorer_results = [
            self.poisson_scorer.score(inp),
            self.market_scorer.score(inp),
            self.context_scorer.score(inp),
            self.resilience_scorer.score(inp),
            self.knockout_scorer.score(inp),
        ]

        # When CRS+handicap strongly disagree with WDL, trust market more
        if crs_orientation_bonus:
            from .aggregator import ScoreAggregator
            orient_weights = dict(self.aggregator.weights)
            orient_weights["poisson"] *= 0.5
            orient_weights["market_crs"] *= 1.8
            orient_aggregator = ScoreAggregator(orient_weights)
            aggregated = orient_aggregator.aggregate(scorer_results)
        else:
            aggregated = self.aggregator.aggregate(scorer_results)
        best = self.aggregator.top_scores(aggregated, n=2)

        # ── Post-processing ──
        # Ensure rout representation for deep favourites
        from service.score_pick import ensure_rout_score_in_likely_pair
        gap = abs(int(rank_a or 50) - int(rank_b or 50))
        best = ensure_rout_score_in_likely_pair(
            best, crs,
            sp_win=sp_win, sp_lose=sp_lose,
            win_rate=adjusted_wr, lose_rate=adjusted_lr,
            rank_gap=gap,
        )

        # WDL alignment: ensure primary score matches dominant direction
        from service.score_pick import align_score_picks_to_wdl
        best = align_score_picks_to_wdl(
            best, crs,
            win_rate=adjusted_wr, draw_rate=adjusted_dr, lose_rate=adjusted_lr,
            model_scores=hints or None,
            group_context={
                **(group_context or {}),
                **({"handicap": handicap} if handicap else {}),
                **({"rank_a": rank_a, "rank_b": rank_b,
                    "rank_gap": gap} if rank_a is not None and rank_b is not None else {}),
            },
        )

        # Contextual modifications (MD3, host opener, etc.)
        from service.score_context import apply_contextual_score_adjustments
        best = apply_contextual_score_adjustments(
            best, crs,
            group_context=group_context,
            odds_dict=inp.odds_dict,
            win_rate=adjusted_wr,
            lose_rate=adjusted_lr,
            draw_rate=adjusted_dr,
            expected_a=expected_a,
            expected_b=expected_b,
            rank_a=rank_a,
            rank_b=rank_b,
            team_a=team_a or {},
            team_b=team_b or {},
        )

        # Resilience adjustments to likely pair
        from service.score_context import detect_resilience_signals, apply_resilience_to_likely_pair
        _res_odds = dict(odds_dict or {})
        if sp_win is not None:
            _res_odds.setdefault("win_win", sp_win)
        if sp_lose is not None:
            _res_odds.setdefault("win_lose", sp_lose)
        if sp_draw is not None:
            _res_odds.setdefault("draw", sp_draw)
        resilience = detect_resilience_signals(
            group_context, _res_odds, rank_a, rank_b,
            team_a=team_a or {}, team_b=team_b or {},
        )
        best = apply_resilience_to_likely_pair(
            best, crs, resilience,
            win_rate=adjusted_wr, lose_rate=adjusted_lr,
        )

        # ── Upset pick ──
        upset = self.upset_picker.pick(aggregated, best, crs, inp)

        from service.score_pick import (
            ensure_knockout_underdog_upset,
            is_knockout_stage,
        )
        if is_knockout_stage(stage):
            upset = ensure_knockout_underdog_upset(
                best, upset,
                win_rate=adjusted_wr,
                lose_rate=adjusted_lr,
                rank_a=rank_a,
                rank_b=rank_b,
                crs=crs,
                stage=stage,
                sp_draw=sp_draw,
            )

        from service.score_pick import ensure_extreme_mismatch_triple_coverage
        best, upset = ensure_extreme_mismatch_triple_coverage(
            best, upset, crs,
            sp_win=sp_win, sp_lose=sp_lose,
            rank_a=rank_a, rank_b=rank_b,
            expected_a=expected_a, expected_b=expected_b,
        )

        # ── Validate ──
        best, upset, warnings = self.validator.validate(
            best, upset, crs,
            model_scores=hints or None,
            win_rate=adjusted_wr,
            draw_rate=adjusted_dr,
            lose_rate=adjusted_lr,
        )

        all_picks = best + ([upset] if upset else [])
        return best, upset, all_picks, warnings

    # ── Pre-processing ──────────────────────────────────────────────────

    @staticmethod
    def _detect_crs_handicap_orientation(
        crs: dict[str, float],
        handicap: str | None,
        win_rate: float, draw_rate: float, lose_rate: float,
    ) -> str:
        """
        Detect when CRS market + handicap strongly disagree with WDL.

        Returns 'home', 'away', or '' — the side the MARKET says is favoured.
        When disagreement is extreme, the pipeline boosts market CRS weight
        and reduces Poisson weight.
        """
        if not crs:
            return ""

        hcp = 0.0
        if handicap:
            try:
                hcp = float(str(handicap).replace("+", ""))
            except (TypeError, ValueError):
                pass

        # Count CRS top-5 outcomes
        ranked = sorted(
            [(k, v) for k, v in crs.items() if ":" in str(k) and float(v) > 0],
            key=lambda x: float(x[1]),
        )[:5]
        if not ranked:
            return ""

        home_wins = sum(1 for s, _ in ranked if ScorePredictionPipeline._outcome(s) == "win")
        away_wins = sum(1 for s, _ in ranked if ScorePredictionPipeline._outcome(s) == "lose")
        draws = sum(1 for s, _ in ranked if ScorePredictionPipeline._outcome(s) == "draw")

        # Market clearly favours away
        if away_wins >= 3 and home_wins == 0 and hcp >= 1.0:
            if lose_rate < win_rate:  # WDL disagrees with market
                return "away"
        # Market clearly favours home
        if home_wins >= 3 and away_wins == 0 and hcp <= -1.0:
            if win_rate < lose_rate:  # WDL disagrees with market
                return "home"

        return ""

    @staticmethod
    def _outcome(score: str) -> str:
        try:
            ga, gb = map(int, score.split(":"))
        except (ValueError, AttributeError):
            return "draw"
        if ga > gb:
            return "win"
        if ga < gb:
            return "lose"
        return "draw"

    @staticmethod
    def _preprocess_wdl(
        win_rate: float, draw_rate: float, lose_rate: float,
        group_context: dict | None, odds_dict: dict | None,
        rank_a: int | None, rank_b: int | None,
        team_a: dict | None, team_b: dict | None,
        sp_win: float | None, sp_lose: float | None,
        sp_draw: float | None, handicap: str | None,
        skip_wdl_resilience: bool,
    ) -> tuple[float, float, float]:
        """Apply resilience WDL adjustments before scoring."""
        if skip_wdl_resilience:
            return win_rate, draw_rate, lose_rate

        from service.score_context import detect_resilience_signals, adjust_wdl_for_resilience

        _res_odds = dict(odds_dict or {})
        if sp_win is not None:
            _res_odds.setdefault("win_win", sp_win)
        if sp_lose is not None:
            _res_odds.setdefault("win_lose", sp_lose)
        if sp_draw is not None:
            _res_odds.setdefault("draw", sp_draw)
        if handicap:
            _res_odds.setdefault("handicap", handicap)

        signals = detect_resilience_signals(
            group_context, _res_odds, rank_a, rank_b,
            team_a=team_a or {}, team_b=team_b or {},
        )
        return adjust_wdl_for_resilience(win_rate, draw_rate, lose_rate, signals)
