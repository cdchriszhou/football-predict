"""
Score Pick Configuration — centralized thresholds for CRS-anchored score selection.

This module provides tunable parameters that were previously hard-coded
throughout score_pick.py and score_context.py.
"""
from __future__ import annotations

from typing import TypedDict


class ScorePickConfig(TypedDict, total=False):
    """All configurable thresholds for score prediction pipeline."""

    # ── Market threshold constants ────────────────────────────────────────────
    HEAVY_FAV_SP_WIN: float          # SPF home fav must be < this to block draw promotion
    HEAVY_FAV_SP_LOSE: float         # SPF away fav must be < this for away-heavy logic
    DRAW_SP_CAP: float               # Max draw odds for promotion to primary
    DRAW_RATE_MIN: float             # Min draw rate for draw promotion
    DRAW_RATE_MIN_PROMO: float       # Min draw rate for CRS draw promotion (lower bar)

    # Heavy favourite detection
    WIN_RATE_HEAVY_HOME: float       # Home win_rate to trigger home-heavy logic
    WIN_RATE_HEAVY_AWAY: float       # Away lose_rate to trigger away-heavy logic
    WIN_RATE_STRONG_HOME: float      # Stricter bar for blowout / 胜其它 paths

    # Competitive match thresholds
    COMPETITIVE_WIN_GAP: float        # |win_rate - lose_rate| to be "competitive"
    COMPETITIVE_DRAW_MIN: float      # Min draw_rate for competitive flag

    # ── CRS odds gap caps ──────────────────────────────────────────────────────
    BLOWOUT_ODD_GAP_DEFAULT: float   # Default max CRS odd gap for rout promotion
    BLOWOUT_ODD_GAP_SP_125: float    # Gap cap when sp_win < 1.25
    BLOWOUT_ODD_GAP_SP_145: float    # Gap cap when sp_win < 1.45
    BLOWOUT_ODD_GAP_SP_165: float    # Gap cap when sp_win < 1.65
    SAME_OUTCOME_GAP_CAP: float       # Max gap for same-outcome alternate (e.g. 2:0 → 2:1)
    HOME_SCORING_GAP_CAP: float       # Max gap for home-scoring-away-win (1:2, 1:3)

    # ── Blowout tiers ──────────────────────────────────────────────────────────
    # Shutout-first tiers: (score, min_xg, max_sp)
    BLOWOUT_TIERS: list[tuple[str, float, float]]
    BLOWOUT_TIERS_HIGH_ONLY: list[tuple[str, float, float]]

    # ── Draw promotion ────────────────────────────────────────────────────────
    DRAW_RATIO_CAP: float            # Max draw_odd/primary_odd for promotion
    DRAW_GAP_CAP: float              # Max (draw_odd - primary_odd) for promotion
    DRAW_RATIO_CAP_STRICT: float     # Tighter ratio for close matches (e.g. Ivory Coast)
    DRAW_GAP_CAP_STRICT: float       # Tighter gap for close matches
    HOME_WIN_GAP_CAP: float           # Gap cap for home_win vs draw

    # ── Stage-based adjustments ────────────────────────────────────────────────
    STAGE_DRAW_BOOST_GROUP: float     # Extra draw weight for 小组赛
    STAGE_DRAW_BOOST_KO: float       # Extra draw weight for knockout rounds
    STAGE_DRAW_BOOST_FINAL: float    # Extra draw weight for 季军赛/决赛

    # ── Resilience adjustment ──────────────────────────────────────────────────
    RESILIENCE_CLEAN_SHEET_BUMP: float  # Draw bump when opponent has clean sheet
    RESILIENCE_SCORING_DROUGHT_BUMP: float  # Draw bump for scoring drought
    RESILIENCE_DEFENSIVE_BUMP: float   # Draw bump for defensive opponent
    RESILIENCE_COMBINED_BUMP: float   # Additional bump for combined signals
    RESILIENCE_DRAW_CAP: float        # Cap for resilience-adjusted draw rate

    # ── Alignment thresholds ───────────────────────────────────────────────────
    ALIGN_MIN_MARGIN: float          # Min WDL margin to trigger alignment
    ALIGN_MARGIN_STRONG: float       # Margin threshold for forcing direction change
    ALIGN_DRAW_PRESERVE_RATE: float  # Draw_rate threshold for preserving draw secondary

    # ── Upset thresholds ───────────────────────────────────────────────────────
    UPSET_DRAW_DEEP_FAV_LIMIT: float  # Max draw CRS odd for deep-fav stalemate upset
    UPSET_AWAY_HOME_SCORE_ODD: float  # Max odd for home 1:0 upset (away fav)
    UPSET_SAME_DIR_ODD_CAP: float     # Max odd for same-direction upset fallback
    UPSET_MIN_ODD_WARNING: float      # Min odd threshold for upset probability warning

    # ── Context thresholds ─────────────────────────────────────────────────────
    DEEP_HANDICAP_THRESHOLD: float    # Handicap value to trigger deep fav logic
    RANK_GAP_BLOWOUT: float          # Min rank gap for rout boost
    RANK_GAP_HEAVY_BOOST: float       # Min rank gap for heavy fav boost
    LOW_TOTAL_THRESHOLD: float        # Over/under line for "low total" detection
    RANK_GAP_STALEMATE: float         # Rank gap for stalemate upset (0:0, 1:1)
    RANK_HIGH_MINNOW: float           # FIFA rank threshold for minnow home upset

    # ── Alignment thresholds ───────────────────────────────────────────────────
    ALIGN_MIN_MARGIN: float          # Min WDL margin to trigger alignment
    ALIGN_MARGIN_STRONG: float       # Margin threshold for forcing direction change
    ALIGN_DRAW_PRESERVE_RATE: float  # Draw_rate threshold for preserving draw secondary
    ALIGN_SAME_DIR_GAP_CAP: float     # Gap cap for same-direction upset fallback

    # ── Upset thresholds ───────────────────────────────────────────────────────
    UPSET_DRAW_DEEP_FAV_LIMIT: float  # Max draw CRS odd for deep-fav stalemate upset
    UPSET_AWAY_HOME_SCORE_ODD: float  # Max odd for home 1:0 upset (away fav)
    UPSET_SAME_DIR_ODD_CAP: float     # Max odd for same-direction upset fallback
    UPSET_MIN_ODD_WARNING: float      # Min odd threshold for upset probability warning
    UPSET_DRAW_RATE_THRESHOLD: float  # Min draw_rate for multi-goal draw upset
    UPSET_MINNOW_HOME_ZERO_ZERO_ODD: float  # Max odd for 0:0 upset when minnow home
    UPSET_DRAW_LOSE_RATE_CAP: float    # Max draw odd when heavy away fav
    UPSET_AWAY_WIN_ODD_CAP: float      # Max odd for away win upset when home fav
    UPSET_CLUSTER_MIN_WIN_RATE: float  # Min win_rate for cluster upset
    UPSET_CONCESSION_ODD_CAP: float    # Max odd for concession upset

    # ── Secondary pick logic ──────────────────────────────────────────────────
    SECONDARY_TIE_TREAT_AS_DIFFERENT: bool  # When 1:0 and 1:1 have same odds, prefer different outcome
    SECONDARY_PROMO_DRAW_CLOSE: float       # Draw_odd - primary_odd cap for 2ndary promotion
    MULTI_GOAL_HOME_FAV_SP_CAP: float        # sp_win cap for multi-goal promotion

    # ── Open game thresholds ──────────────────────────────────────────────────
    OPEN_GAME_BOTH_SCORE_MIN_XG: float  # Min expected goals for both-can-score
    OPEN_GAME_HIGH_TOTAL_THRESHOLD: float  # Min total XG for high-score promotion
    OPEN_GAME_TOTAL_GAP_CAP: float       # Gap cap for open game high score

    # ── Validation thresholds ─────────────────────────────────────────────────
    MIN_TRIPLE_DIRECTION_COVERAGE: int  # Min distinct W/D/L outcomes required
    UPSET_ODD_WARN_CAP: float          # Max odd for upset warning threshold

    # ── New: Scorer weights for weighted ensemble pipeline ────────────────
    POISSON_SCORER_WEIGHT: float       # Default 0.50 — Poisson model dominance
    MARKET_CRS_SCORER_WEIGHT: float    # Default 0.30 — CRS market validation
    CONTEXT_SCORER_WEIGHT: float       # Default 0.15 — situational adjustments
    RESILIENCE_SCORER_WEIGHT: float    # Default 0.05 — defensive/drought signals
    PIPELINE_USE_NEW_ENSEMBLE: bool    # Toggle new vs old pipeline
    AGGREGATOR_MIN_WEIGHT: float       # Filter noise below this weight

    # ── New: Knockout stage parameters ───────────────────────────────────
    KNOCKOUT_SCORER_WEIGHT: float      # Weight for knockout-specific scorer
    KO_ROUND_PARAMS: dict              # Per-round params {stage: {goal_reduction, draw_boost, et_base}}


# ── Default configuration ──────────────────────────────────────────────────────
DEFAULT_CONFIG: ScorePickConfig = {
    # Market threshold constants
    "HEAVY_FAV_SP_WIN": 1.55,
    "HEAVY_FAV_SP_LOSE": 1.55,
    "DRAW_SP_CAP": 3.7,
    "DRAW_RATE_MIN": 26.0,
    "DRAW_RATE_MIN_PROMO": 30.0,

    # Heavy favourite detection
    "WIN_RATE_HEAVY_HOME": 58.0,
    "WIN_RATE_HEAVY_AWAY": 55.0,
    "WIN_RATE_STRONG_HOME": 65.0,

    # Competitive match thresholds
    "COMPETITIVE_WIN_GAP": 28.0,
    "COMPETITIVE_DRAW_MIN": 18.0,

    # CRS odds gap caps
    "BLOWOUT_ODD_GAP_DEFAULT": 5.0,
    "BLOWOUT_ODD_GAP_SP_125": 8.0,
    "BLOWOUT_ODD_GAP_SP_145": 6.5,
    "BLOWOUT_ODD_GAP_SP_165": 5.0,
    "SAME_OUTCOME_GAP_CAP": 5.0,
    "HOME_SCORING_GAP_CAP": 6.0,

    # Blowout tiers: (score, min_xg, max_sp)
    # Blowout tiers (添加极端比分覆盖大比分比赛)
    "BLOWOUT_TIERS": [
        ("4:0", 1.75, 1.35),
        ("3:0", 1.50, 1.55),
        ("5:0", 2.00, 1.25),
        ("6:0", 2.50, 1.18),
        ("7:0", 3.00, 1.15),
        ("4:1", 1.85, 1.55),
        ("3:1", 1.65, 1.50),
        ("6:1", 2.80, 1.20),
        ("7:1", 3.20, 1.18),
    ],
    "BLOWOUT_TIERS_HIGH_ONLY": [
        ("4:0", 1.75, 1.35),
        ("3:0", 1.50, 1.55),
        ("5:0", 2.00, 1.25),
        ("6:0", 2.50, 1.18),
        ("7:0", 3.00, 1.15),
        ("4:1", 1.85, 1.55),
        ("3:1", 1.65, 1.50),
    ],

    # Draw promotion
    "DRAW_RATIO_CAP": 1.55,
    "DRAW_GAP_CAP": 2.0,
    "DRAW_RATIO_CAP_STRICT": 1.15,
    "DRAW_GAP_CAP_STRICT": 1.2,
    "HOME_WIN_GAP_CAP": 4.0,

    # Stage-based adjustments (KO lowered — 2026 R16+ had 7/8 non-draw results)
    "STAGE_DRAW_BOOST_GROUP": 3.0,
    "STAGE_DRAW_BOOST_KO": 3.0,
    "STAGE_DRAW_BOOST_FINAL": 2.5,

    # Resilience adjustment (降低50%权重以避免过度预测平局)
    "RESILIENCE_CLEAN_SHEET_BUMP": 5.0,
    "RESILIENCE_SCORING_DROUGHT_BUMP": 4.0,
    "RESILIENCE_DEFENSIVE_BUMP": 2.5,
    "RESILIENCE_COMBINED_BUMP": 2.0,
    "RESILIENCE_DRAW_CAP": 30.0,

    # Alignment thresholds
    "ALIGN_MIN_MARGIN": 6.0,
    "ALIGN_MARGIN_STRONG": 8.0,
    "ALIGN_DRAW_PRESERVE_RATE": 20.0,

    # Upset thresholds
    "UPSET_DRAW_DEEP_FAV_LIMIT": 55.0,
    "UPSET_AWAY_HOME_SCORE_ODD": 9.0,
    "UPSET_SAME_DIR_ODD_CAP": 14.0,
    "UPSET_MIN_ODD_WARNING": 25.0,

    # Context thresholds
    "DEEP_HANDICAP_THRESHOLD": -1.5,
    "RANK_GAP_BLOWOUT": 50.0,
    "RANK_GAP_HEAVY_BOOST": 25.0,
    "LOW_TOTAL_THRESHOLD": 2.5,
    "RANK_GAP_STALEMATE": 30.0,
    "RANK_HIGH_MINNOW": 75.0,

    # Alignment thresholds
    "ALIGN_MIN_MARGIN": 6.0,
    "ALIGN_MARGIN_STRONG": 8.0,
    "ALIGN_DRAW_PRESERVE_RATE": 20.0,
    "ALIGN_SAME_DIR_GAP_CAP": 8.0,

    # Upset thresholds
    "UPSET_DRAW_DEEP_FAV_LIMIT": 55.0,
    "UPSET_AWAY_HOME_SCORE_ODD": 9.0,
    "UPSET_SAME_DIR_ODD_CAP": 14.0,
    "UPSET_MIN_ODD_WARNING": 25.0,
    "UPSET_DRAW_RATE_THRESHOLD": 18.0,
    "UPSET_MINNOW_HOME_ZERO_ZERO_ODD": 12.0,
    "UPSET_DRAW_LOSE_RATE_CAP": 9.5,
    "UPSET_AWAY_WIN_ODD_CAP": 18.0,
    "UPSET_CLUSTER_MIN_WIN_RATE": 52.0,
    "UPSET_CONCESSION_ODD_CAP": 22.0,

    # Secondary pick logic
    "SECONDARY_TIE_TREAT_AS_DIFFERENT": True,
    "SECONDARY_PROMO_DRAW_CLOSE": 1.2,
    "MULTI_GOAL_HOME_FAV_SP_CAP": 1.70,

    # Open game thresholds
    "OPEN_GAME_BOTH_SCORE_MIN_XG": 1.25,
    "OPEN_GAME_HIGH_TOTAL_THRESHOLD": 4.0,
    "OPEN_GAME_TOTAL_GAP_CAP": 12.0,

    # Validation thresholds
    "MIN_TRIPLE_DIRECTION_COVERAGE": 3,
    "UPSET_ODD_WARN_CAP": 20.0,

    # New: Scorer weights for weighted ensemble pipeline
    "POISSON_SCORER_WEIGHT": 0.50,
    "MARKET_CRS_SCORER_WEIGHT": 0.35,
    "CONTEXT_SCORER_WEIGHT": 0.15,
    "RESILIENCE_SCORER_WEIGHT": 0.05,
    "PIPELINE_USE_NEW_ENSEMBLE": True,
    "AGGREGATOR_MIN_WEIGHT": 0.001,

    # New: Knockout stage parameters
    "KNOCKOUT_SCORER_WEIGHT": 0.10,
    "KO_ROUND_PARAMS": {
        "1/16决赛": {"goal_reduction": 0.92, "draw_boost": 3.0, "et_base": 0.12},
        "1/8决赛": {"goal_reduction": 0.90, "draw_boost": 3.0, "et_base": 0.12},
        "1/4决赛": {"goal_reduction": 0.88, "draw_boost": 3.5, "et_base": 0.14},
        "半决赛":  {"goal_reduction": 0.85, "draw_boost": 3.0, "et_base": 0.16},
        "决赛":    {"goal_reduction": 0.90, "draw_boost": 2.8, "et_base": 0.14},
        "季军赛":  {"goal_reduction": 0.90, "draw_boost": 2.8, "et_base": 0.10},
    },
}


# ── Runtime config store ───────────────────────────────────────────────────────
_config: ScorePickConfig = {}


def load_config(overrides: ScorePickConfig | None = None) -> ScorePickConfig:
    """Load configuration with optional overrides (e.g. from database/API)."""
    global _config
    _config = {**DEFAULT_CONFIG, **(overrides or {})}
    return _config


def get_config() -> ScorePickConfig:
    """Get current configuration, loading defaults if not yet initialized."""
    if not _config:
        load_config()
    return _config


def get(key: str, default: float | str | bool | None = None) -> float | str | bool | None:
    """Get a single config value by key."""
    return _config.get(key, DEFAULT_CONFIG.get(key, default))


# ── Convenience accessors ───────────────────────────────────────────────────────
def heavy_fav_sp_win() -> float:
    return float(get("HEAVY_FAV_SP_WIN", 1.55))


def heavy_fav_sp_lose() -> float:
    return float(get("HEAVY_FAV_SP_LOSE", 1.55))


def draw_sp_cap() -> float:
    return float(get("DRAW_SP_CAP", 3.7))


def draw_rate_min() -> float:
    return float(get("DRAW_RATE_MIN", 26.0))


def blowout_odd_gap_cap(sp_win: float | None = None, expected_a: float = 1.2) -> float:
    """Calculate blowout CRS odd gap cap based on sp_win and expected goals."""
    if sp_win is None:
        return float(get("BLOWOUT_ODD_GAP_DEFAULT", 5.0))
    if sp_win < 1.25:
        return float(get("BLOWOUT_ODD_GAP_SP_125", 8.0))
    if sp_win < 1.45:
        return float(get("BLOWOUT_ODD_GAP_SP_145", 6.5))
    if sp_win < 1.65:
        return float(get("BLOWOUT_ODD_GAP_SP_165", 5.0))
    return float(get("BLOWOUT_ODD_GAP_DEFAULT", 5.0))


def is_heavy_fav_away(lose_rate: float, sp_lose: float | None) -> bool:
    return lose_rate >= float(get("WIN_RATE_HEAVY_AWAY", 55.0)) or (
        sp_lose is not None and sp_lose < heavy_fav_sp_lose()
    )


def is_heavy_fav_home(win_rate: float, sp_win: float | None) -> bool:
    return win_rate >= float(get("WIN_RATE_HEAVY_HOME", 58.0)) or (
        sp_win is not None and sp_win < heavy_fav_sp_win()
    )


def is_strong_home_fav(win_rate: float, sp_win: float | None) -> bool:
    """Stricter bar for blowout / 胜其它 upset paths."""
    if win_rate >= float(get("WIN_RATE_STRONG_HOME", 65.0)):
        return True
    return sp_win is not None and sp_win < 1.50


def draw_ratio_cap() -> float:
    return float(get("DRAW_RATIO_CAP", 1.55))


def draw_gap_cap() -> float:
    return float(get("DRAW_GAP_CAP", 2.0))


def stage_draw_boost(stage: str | None) -> float:
    """Extra draw weight for CRS draw-promotion rules by stage."""
    if not stage:
        return 0.0
    if stage == "小组赛":
        return float(get("STAGE_DRAW_BOOST_GROUP", 5.0))
    if stage in ("1/16决赛", "1/8决赛", "1/4决赛", "半决赛"):
        return float(get("STAGE_DRAW_BOOST_KO", 8.0))
    if stage in ("季军赛", "决赛"):
        return float(get("STAGE_DRAW_BOOST_FINAL", 4.0))
    return 0.0


def resilience_draw_bump(signals: dict) -> float:
    """Calculate total resilience draw bump from signals."""
    bump = 0.0
    cfg = get_config()
    if signals.get("opponent_clean_sheet"):
        bump += float(cfg.get("RESILIENCE_CLEAN_SHEET_BUMP", 10.0))
    if signals.get("favorite_scoring_drought"):
        bump += float(cfg.get("RESILIENCE_SCORING_DROUGHT_BUMP", 8.0))
    if signals.get("opponent_defensive"):
        bump += float(cfg.get("RESILIENCE_DEFENSIVE_BUMP", 5.0))
    if (
        signals.get("group_low_scoring")
        and (signals.get("opponent_clean_sheet") or signals.get("favorite_scoring_drought"))
    ):
        bump += float(cfg.get("RESILIENCE_COMBINED_BUMP", 4.0))
    return bump


# ── Configuration validation ──────────────────────────────────────────────────
def validate_config_bounds(config: ScorePickConfig | None = None) -> list[str]:
    """Validate configuration parameters are within reasonable bounds."""
    cfg = config or get_config()
    warnings: list[str] = []

    # Market threshold bounds
    if cfg.get("HEAVY_FAV_SP_WIN", 1.55) < 1.10 or cfg.get("HEAVY_FAV_SP_WIN", 1.55) > 2.50:
        warnings.append("HEAVY_FAV_SP_WIN outside reasonable range [1.10, 2.50]")
    if cfg.get("HEAVY_FAV_SP_LOSE", 1.55) < 1.10 or cfg.get("HEAVY_FAV_SP_LOSE", 1.55) > 2.50:
        warnings.append("HEAVY_FAV_SP_LOSE outside reasonable range [1.10, 2.50]")
    if cfg.get("DRAW_SP_CAP", 3.7) < 2.5 or cfg.get("DRAW_SP_CAP", 3.7) > 5.5:
        warnings.append("DRAW_SP_CAP outside reasonable range [2.5, 5.5]")
    if cfg.get("DRAW_RATE_MIN", 26.0) < 15.0 or cfg.get("DRAW_RATE_MIN", 26.0) > 45.0:
        warnings.append("DRAW_RATE_MIN outside reasonable range [15.0, 45.0]")

    # Win rate thresholds
    if cfg.get("WIN_RATE_HEAVY_HOME", 58.0) < 45.0 or cfg.get("WIN_RATE_HEAVY_HOME", 58.0) > 75.0:
        warnings.append("WIN_RATE_HEAVY_HOME outside reasonable range [45.0, 75.0]")
    if cfg.get("WIN_RATE_HEAVY_AWAY", 55.0) < 45.0 or cfg.get("WIN_RATE_HEAVY_AWAY", 55.0) > 75.0:
        warnings.append("WIN_RATE_HEAVY_AWAY outside reasonable range [45.0, 75.0]")
    if cfg.get("WIN_RATE_STRONG_HOME", 65.0) < 50.0 or cfg.get("WIN_RATE_STRONG_HOME", 65.0) > 85.0:
        warnings.append("WIN_RATE_STRONG_HOME outside reasonable range [50.0, 85.0]")

    # CRS odds gap caps
    gap_default = cfg.get("BLOWOUT_ODD_GAP_DEFAULT", 5.0)
    if gap_default < 3.0 or gap_default > 15.0:
        warnings.append("BLOWOUT_ODD_GAP_DEFAULT outside reasonable range [3.0, 15.0]")

    # Alignment thresholds
    if cfg.get("ALIGN_MIN_MARGIN", 6.0) < 2.0 or cfg.get("ALIGN_MIN_MARGIN", 6.0) > 15.0:
        warnings.append("ALIGN_MIN_MARGIN outside reasonable range [2.0, 15.0]")
    if cfg.get("ALIGN_MARGIN_STRONG", 8.0) < 4.0 or cfg.get("ALIGN_MARGIN_STRONG", 8.0) > 20.0:
        warnings.append("ALIGN_MARGIN_STRONG outside reasonable range [4.0, 20.0]")

    # Upset thresholds
    if cfg.get("UPSET_DRAW_DEEP_FAV_LIMIT", 55.0) < 25.0 or cfg.get("UPSET_DRAW_DEEP_FAV_LIMIT", 55.0) > 80.0:
        warnings.append("UPSET_DRAW_DEEP_FAV_LIMIT outside reasonable range [25.0, 80.0]")
    if cfg.get("UPSET_MIN_ODD_WARNING", 20.0) < 10.0 or cfg.get("UPSET_MIN_ODD_WARNING", 20.0) > 40.0:
        warnings.append("UPSET_MIN_ODD_WARNING outside reasonable range [10.0, 40.0]")

    # Resilience bump caps
    if cfg.get("RESILIENCE_DRAW_CAP", 40.0) < 25.0 or cfg.get("RESILIENCE_DRAW_CAP", 40.0) > 50.0:
        warnings.append("RESILIENCE_DRAW_CAP outside reasonable range [25.0, 50.0]")

    # Context thresholds
    rank_gap = cfg.get("RANK_GAP_BLOWOUT", 50.0)
    if rank_gap < 15.0 or rank_gap > 100.0:
        warnings.append("RANK_GAP_BLOWOUT outside reasonable range [15.0, 100.0]")

    return warnings


def safe_load_config(overrides: ScorePickConfig | None = None) -> ScorePickConfig:
    """Load configuration with validation warnings."""
    config = load_config(overrides)
    warnings = validate_config_bounds(config)
    if warnings:
        import warnings as warn_module
        for w in warnings:
            warn_module.warn(f"Configuration validation: {w}", stacklevel=2)
    return config
