"""
Unified match / score confidence — avoids flat caps (e.g. every pick at 88%).

Score picks are inherently noisier than WDL; confidence reflects CRS implied
probability, model–market alignment, group-stage context, and pick rank.
"""
from __future__ import annotations


def outcome_from_score(score: str) -> str:
    try:
        ga, gb = map(int, score.split(":"))
    except (ValueError, AttributeError):
        return "draw"
    if ga > gb:
        return "win"
    if ga < gb:
        return "lose"
    return "draw"


def _wdl_spread(blend: dict[str, float] | None) -> float:
    if not blend:
        return 0.0
    rates = sorted(blend.values(), reverse=True)
    if len(rates) < 2:
        return 0.0
    return rates[0] - rates[1]


def _count_wdl_agreement(
    pick_code: str,
    *,
    ai: dict | None,
    rule: dict | None,
    market: dict | None,
) -> int:
    agree = 0
    for m in (ai, rule):
        if not m:
            continue
        rates = {"win": m.get("win", 0), "draw": m.get("draw", 0), "lose": m.get("lose", 0)}
        if rates and max(rates, key=rates.get) == pick_code:
            agree += 1
    if market and market.get("has_real_market"):
        imp = {
            "win": market.get("imp_win", 0),
            "draw": market.get("imp_draw", 0),
            "lose": market.get("imp_lose", 0),
        }
        if max(imp, key=imp.get) == pick_code:
            agree += 1
    return agree


def compute_wdl_confidence(
    *,
    pick_code: str,
    blend_pct: float,
    confidence_penalty: float = 0.0,
    alerts: list[str] | None = None,
    ai_confidence: float | None = None,
    model_agreements: int | None = None,
    ai: dict | None = None,
    rule: dict | None = None,
    market: dict | None = None,
    teams_available: bool = False,
    matchday: int = 0,
    blend: dict[str, float] | None = None,
    pick_warnings: list[str] | None = None,
) -> float:
    """Overall WDL prediction confidence (stored on Prediction / 胜平负方案)."""
    if model_agreements is None:
        model_agreements = _count_wdl_agreement(
            pick_code, ai=ai, rule=rule, market=market,
        )

    base = 0.46 + model_agreements * 0.05
    base += min(0.10, max(0.0, (blend_pct - 33.0) / 250.0))

    if ai_confidence is not None:
        base = base * 0.62 + float(ai_confidence) * 0.38

    if teams_available:
        base += 0.03

    spread = _wdl_spread(blend)
    if spread < 8.0:
        base -= 0.07
    elif spread < 14.0:
        base -= 0.03

    if matchday >= 2:
        base -= 0.03

    for alert in alerts or []:
        if any(k in alert for k in ("冷门", "分歧", "默契", "盘口异常")):
            base -= 0.04
            break

    base -= confidence_penalty

    if pick_warnings:
        base -= min(0.08, len(pick_warnings) * 0.04)

    return round(max(0.38, min(0.86, base)), 2)


def compute_score_confidence(
    *,
    scoreline: str,
    rank: int,
    model_scores: list[str],
    crs_odd: float | None = None,
    blend: dict[str, float] | None = None,
    confidence_penalty: float = 0.0,
    alerts: list[str] | None = None,
    ai_confidence: float | None = None,
    teams_available: bool = False,
    matchday: int = 0,
    is_upset: bool = False,
    pick_warnings: list[str] | None = None,
) -> float:
    """CRS score pick confidence — lower ceiling than WDL; varies by rank & market."""
    rank = max(0, rank)
    base = {0: 0.40, 1: 0.34, 2: 0.28}.get(rank, 0.26)
    base -= rank * 0.02

    if crs_odd and crs_odd > 1.01:
        implied_pct = 100.0 / crs_odd
        base += min(0.14, implied_pct / 100.0 * 0.75)

    if blend:
        outcome = outcome_from_score(scoreline)
        fav = max(blend, key=blend.get)
        fav_pct = blend.get(fav, 33.0)
        if outcome == fav:
            base += min(0.06, max(0.0, (fav_pct - 40.0) / 200.0))
        else:
            base -= 0.06

        spread = _wdl_spread(blend)
        if spread < 10.0:
            base -= 0.05

    if scoreline in model_scores[:1]:
        base += 0.04
    elif scoreline in model_scores[:3]:
        base += 0.02

    if ai_confidence is not None:
        ai_weight = max(0.15, 0.32 - rank * 0.08)
        base = base * (1.0 - ai_weight) + float(ai_confidence) * ai_weight

    if teams_available:
        base += 0.02

    if matchday >= 2:
        base -= 0.04

    for alert in alerts or []:
        if any(k in alert for k in ("冷门", "分歧", "需抢分", "默契")):
            base -= 0.03

    if pick_warnings:
        base -= min(0.06, len(pick_warnings) * 0.03)

    base -= confidence_penalty

    ceiling = 0.52 if is_upset else {0: 0.74, 1: 0.66, 2: 0.58}.get(rank, 0.55)
    return round(max(0.35, min(ceiling, base)), 2)
