"""
Handicap & Over/Under → Expected Goals converter.

Converts Asian handicap lines + juice and Over/Under lines + juice
into expected goal margin and total goal estimates for score prediction.
"""
from __future__ import annotations

from typing import Optional


def handicap_to_xg_margin(
    handicap_line: float,
    handicap_win_odds: Optional[float] = None,
    handicap_lose_odds: Optional[float] = None,
) -> float:
    """
    Convert Asian handicap line + water level to expected goal margin.

    The handicap line gives the base expected margin. The juice (water level)
    reveals the market's directional bias around that line.

    Formula:
        margin = abs(handicap_line) + (fav_odds - dog_odds) * 0.30
        sign = -1 if handicap_line < 0 else +1

    Examples:
        -1.5 @ 1.85/2.05 → 1.5 + (1.85-2.05)*0.30 = 1.44 goals (fav by 1.44)
        -0.5 @ 1.90/1.90 → 0.5 + 0 = 0.50 goals
        -1.0 @ 1.80/2.10 → 1.0 + (1.80-2.10)*0.30 = 0.91 goals
        +1.5 @ 2.05/1.85 → 1.5 + (2.05-1.85)*0.30 = 1.56 goals (dog expected to lose by 1.56)
    """
    if handicap_line == 0:
        return 0.0

    base_margin = abs(handicap_line)
    sign = -1 if handicap_line < 0 else 1

    # Juice adjustment: when fav odds are lower than dog odds,
    # market is slightly more confident in the favourite covering
    juice_adjustment = 0.0
    if handicap_win_odds is not None and handicap_lose_odds is not None:
        if handicap_line < 0:
            # Home is favourite — fav_odds = handicap_win, dog_odds = handicap_lose
            juice_adjustment = (handicap_win_odds - handicap_lose_odds) * 0.30
        else:
            # Away is favourite — fav_odds = handicap_lose, dog_odds = handicap_win
            juice_adjustment = (handicap_lose_odds - handicap_win_odds) * 0.30

    margin = base_margin + juice_adjustment
    # Quarter-ball handicap: market expects ~0.25 goal advantage
    if abs(handicap_line) < 0.5 and abs(handicap_line) > 0:
        margin = max(0.10, margin)

    return max(0.05, margin) * sign


def over_under_to_total_xg(
    ou_line: float,
    over_odds: Optional[float] = None,
    under_odds: Optional[float] = None,
) -> float:
    """
    Convert Over/Under line + juice to expected total goals.

    When over_odds < under_odds, market expects goals above the line.
    When under_odds < over_odds, market expects goals below the line.

    Formula:
        total = ou_line + (under_odds - over_odds) * 0.40

    Examples:
        2.5 @ 1.90/1.90 → 2.5 + 0 = 2.50 goals
        2.5 @ 1.80/2.10 → 2.5 + (2.10-1.80)*0.40 = 2.62 (market leans over)
        2.5 @ 2.10/1.80 → 2.5 + (1.80-2.10)*0.40 = 2.38 (market leans under)
        3.0 @ 1.85/2.05 → 3.0 + (2.05-1.85)*0.40 = 3.08 (high-scoring expected)
    """
    juice_adjustment = 0.0
    if over_odds is not None and under_odds is not None:
        juice_adjustment = (under_odds - over_odds) * 0.40

    return max(1.5, min(4.5, ou_line + juice_adjustment))


def estimate_et_probability(
    rank_gap: int = 0,
    draw_odds: Optional[float] = None,
    imp_draw: float = 25.0,
    stage: str = "",
) -> float:
    """
    Estimate probability that the match goes to extra time (draw in 90 minutes).

    Knockout matches have higher draw rates than group stage due to conservative
    tactics. This model combines structural factors (stage, rank gap) with
    market signals (draw odds) to estimate extra time probability.

    Base rates by round (from historical World Cup data):
        R16: ~18%, QF: ~20%, SF: ~22%, Final: ~25%, 3rd-place: ~10%
    """
    from service.score_pick_config import get_config
    cfg = get_config()
    ko_params = cfg.get("KO_ROUND_PARAMS", {})
    params = ko_params.get(stage, {})
    base = float(params.get("et_base", 0.20))

    # Rank gap: closer ranks → more likely to draw
    if rank_gap < 10:
        base += 0.05
    elif rank_gap > 30:
        base -= 0.06

    # Market draw odds signal
    if draw_odds is not None:
        if draw_odds < 3.0:
            base += 0.08  # strong draw protection
        elif draw_odds < 3.3:
            base += 0.04
        elif draw_odds > 4.5:
            base -= 0.06  # market expects a winner in 90 min

    # Market implied draw probability
    if imp_draw > 35:
        base += 0.06
    elif imp_draw > 30:
        base += 0.03
    elif imp_draw < 22:
        base -= 0.04

    return round(max(0.08, min(0.38, base)), 2)


def handicap_to_score_weights(
    handicap_line: float,
    handicap_win_odds: Optional[float],
    handicap_lose_odds: Optional[float],
    score_odds: dict[str, float],
    win_rate: float,
    lose_rate: float,
) -> dict[str, float]:
    """
    Convert handicap expectation to additive score weights.

    Based on the expected margin from the handicap, boost scorelines
    that match the expected margin and demote scores that contradict it.
    """
    margin = handicap_to_xg_margin(handicap_line, handicap_win_odds, handicap_lose_odds)
    weights: dict[str, float] = {}

    is_home_fav = margin < 0  # negative handicap = home favoured
    abs_margin = abs(margin)

    for score in score_odds:
        if ":" not in str(score):
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue

        actual_margin = ga - gb
        margin_diff = abs(actual_margin - margin)

        # Boost scores close to the expected margin
        if margin_diff < 0.3:
            weights[score] = weights.get(score, 0) + 0.30
        elif margin_diff < 0.7:
            weights[score] = weights.get(score, 0) + 0.15
        elif margin_diff < 1.2:
            weights[score] = weights.get(score, 0) + 0.06

        # Demote scores that strongly contradict the handicap
        if is_home_fav and actual_margin < -3:
            weights[score] = weights.get(score, 0) - 0.25
        elif not is_home_fav and actual_margin > 3:
            weights[score] = weights.get(score, 0) - 0.25

    return weights


def over_under_to_score_weights(
    ou_line: float,
    over_odds: Optional[float],
    under_odds: Optional[float],
    score_odds: dict[str, float],
) -> dict[str, float]:
    """
    Convert Over/Under expectation to additive score weights.

    Boost scores whose total goals match the O/U expectation,
    demote scores whose totals are far from it.
    """
    total = over_under_to_total_xg(ou_line, over_odds, under_odds)
    weights: dict[str, float] = {}

    for score in score_odds:
        if ":" not in str(score):
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue

        actual_total = ga + gb
        total_diff = abs(actual_total - total)

        if total_diff < 0.3:
            weights[score] = weights.get(score, 0) + 0.25
        elif total_diff < 0.7:
            weights[score] = weights.get(score, 0) + 0.12
        elif total_diff > 2.5:
            weights[score] = weights.get(score, 0) - 0.30

    return weights
