"""
Multi-market odds fusion: European (1X2) + Macau/Asian handicap.

Fuses implied probabilities from multiple bookmaker styles and detects
market anomaly signals (divergence, shallow lines, draw protection).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Optional


# Source reliability weights (sum used for normalization)
SOURCE_WEIGHTS = {
    "european": 0.55,
    "macau": 0.45,
}


@dataclass
class FusedOdds:
  """Unified odds view after multi-market fusion."""
  win_win: float
  draw: float
  win_lose: float
  handicap: str = "0"
  handicap_win: float = 0.0
  handicap_draw: float = 0.0
  handicap_lose: float = 0.0
  over_under: str = "2.5"
  over_odds: float = 1.9
  under_odds: float = 1.9
  score_odds: dict = field(default_factory=dict)
  half_full_odds: dict = field(default_factory=dict)
  imp_win: float = 0.0
  imp_draw: float = 0.0
  imp_lose: float = 0.0
  sources_used: list = field(default_factory=list)
  market_signals: dict = field(default_factory=dict)


def implied_probs(win: float, draw: float, lose: float) -> dict:
    """Overround-adjusted 1X2 implied probabilities (percentages)."""
    if not all(v and v > 0 for v in (win, draw, lose)):
        return {}
    overround = 1 / win + 1 / draw + 1 / lose
    return {
        "imp_win": (1 / win) / overround * 100,
        "imp_draw": (1 / draw) / overround * 100,
        "imp_lose": (1 / lose) / overround * 100,
        "overround": (overround - 1) * 100,
    }


def _parse_handicap(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace("+", ""))
    except ValueError:
        return 0.0


def derive_macau_from_european(euro: dict) -> dict:
    """Derive Macau-style Asian handicap odds from European 1X2.

    Macau books typically:
    - Price draws more sharply in collusion-prone scenarios
    - Use quarter-ball handicaps with water-level adjustments
    """
    win = euro.get("win_win", 2.0)
    draw = euro.get("draw", 3.2)
    lose = euro.get("win_lose", 3.5)
    imp = implied_probs(win, draw, lose)
    if not imp:
        return euro.copy()

    fav_is_a = imp["imp_win"] >= imp["imp_lose"]
    gap = abs(imp["imp_win"] - imp["imp_lose"])

    if gap > 35:
        handicap = "-1.5" if fav_is_a else "+1.5"
    elif gap > 20:
        handicap = "-1" if fav_is_a else "+1"
    elif gap > 10:
        handicap = "-0.5" if fav_is_a else "+0.5"
    else:
        handicap = "0"

    h = _parse_handicap(handicap)
    # Macau draw odds often slightly lower than Euro when draw is likely
    macau_draw = round(draw * (0.94 if imp["imp_draw"] > 28 else 0.97), 2)
    macau_win = round(win * (1.02 if h < 0 else 0.99), 2)
    macau_lose = round(lose * (1.02 if h > 0 else 0.99), 2)

    hw = round(1.85 + gap * 0.004, 2)
    hl = round(2.05 - gap * 0.003, 2)
    if fav_is_a:
        handicap_win, handicap_lose = hw, hl
    else:
        handicap_win, handicap_lose = hl, hw

    return {
        "win_win": macau_win,
        "draw": macau_draw,
        "win_lose": macau_lose,
        "handicap": handicap,
        "handicap_win": handicap_win,
        "handicap_draw": round(3.2 + (30 - imp["imp_draw"]) * 0.02, 2),
        "handicap_lose": handicap_lose,
        "over_under": euro.get("over_under", "2.5"),
        "over_odds": euro.get("over_odds", 1.9),
        "under_odds": euro.get("under_odds", 1.9),
        "source": "macau_derived",
    }


def detect_market_signals(
    european: dict,
    macau: dict,
    fundamentals_win_pct: float = 50.0,
) -> dict:
    """Detect market anomalies: traps, draw protection, Euro-Macau divergence."""
    signals = {
        "euro_macau_divergence": 0.0,
        "shallow_handicap_trap": False,
        "draw_protection": False,
        "underdog_value": False,
        "manipulation_risk": 0.0,
        "alerts": [],
    }

    e_imp = implied_probs(
        european.get("win_win"), european.get("draw"), european.get("win_lose")
    )
    m_imp = implied_probs(
        macau.get("win_win"), macau.get("draw"), macau.get("win_lose")
    )
    if not e_imp or not m_imp:
        return signals

    signals["euro_macau_divergence"] = round(
        abs(e_imp["imp_win"] - m_imp["imp_win"])
        + abs(e_imp["imp_draw"] - m_imp["imp_draw"]) * 0.5,
        1,
    )

    if signals["euro_macau_divergence"] > 8:
        signals["alerts"].append(
            f"欧盘与澳盘隐含概率分歧{signals['euro_macau_divergence']:.0f}%，存在盘口博弈"
        )
        signals["manipulation_risk"] += 0.15

    # Shallow handicap trap: strong favorite but shallow Asian line
    fav_pct = max(e_imp["imp_win"], e_imp["imp_lose"])
    h = _parse_handicap(macau.get("handicap", european.get("handicap", 0)))
    if fav_pct > 60 and abs(h) < 0.75:
        signals["shallow_handicap_trap"] = True
        signals["manipulation_risk"] += 0.20
        signals["alerts"].append("强队浅盘：庄家对大胜信心不足，谨防冷门")

    # Draw protection
    draw_o = min(european.get("draw", 99), macau.get("draw", 99))
    if draw_o < 3.2:
        signals["draw_protection"] = True
        signals["manipulation_risk"] += 0.12
        signals["alerts"].append(f"平赔极低({draw_o:.2f})：庄家防范平局")

    # Fundamentals vs market divergence (potential upset or trap)
    fund_gap = abs(fundamentals_win_pct - e_imp["imp_win"])
    if fund_gap > 20:
        if e_imp["imp_win"] < fundamentals_win_pct:
            signals["underdog_value"] = True
            signals["alerts"].append("市场低估主队：存在冷门空间")
        else:
            signals["alerts"].append("市场高估主队：谨防热门翻车")
        signals["manipulation_risk"] += min(0.25, fund_gap / 100)

    signals["manipulation_risk"] = round(min(1.0, signals["manipulation_risk"]), 2)
    return signals


def fuse_multi_market_odds(
    european: dict = None,
    macau: dict = None,
    derived: dict = None,
    fundamentals_win_pct: float = 50.0,
) -> FusedOdds:
    """Fuse real European + Asian handicap odds only (no derived fallback)."""
    sources = []
    weighted_imp = {"imp_win": 0.0, "imp_draw": 0.0, "imp_lose": 0.0}
    total_w = 0.0

    if european and european.get("win_win"):
        imp = implied_probs(european["win_win"], european["draw"], european["win_lose"])
        if imp:
            w = SOURCE_WEIGHTS["european"]
            for k in weighted_imp:
                weighted_imp[k] += imp[k] * w
            total_w += w
            sources.append(european.get("source") or "european")

    if macau and macau.get("win_win"):
        imp = implied_probs(macau["win_win"], macau["draw"], macau["win_lose"])
        if imp:
            w = SOURCE_WEIGHTS["macau"]
            for k in weighted_imp:
                weighted_imp[k] += imp[k] * w
            total_w += w
            sources.append(macau.get("source") or "macau")

    if total_w <= 0:
        return FusedOdds(
            win_win=0, draw=0, win_lose=0,
            sources_used=[],
            market_signals={"alerts": ["无真实外围盘口数据"]},
        )

    for k in weighted_imp:
        weighted_imp[k] /= total_w

    # Convert fused implied probs back to decimal odds
    margin = 1.06
    win_win = round(margin / (weighted_imp["imp_win"] / 100), 2) if weighted_imp["imp_win"] else 2.5
    draw = round(margin / (weighted_imp["imp_draw"] / 100), 2) if weighted_imp["imp_draw"] else 3.2
    win_lose = round(margin / (weighted_imp["imp_lose"] / 100), 2) if weighted_imp["imp_lose"] else 3.0

    base = european or macau or {}
    macau_ref = macau or {}

    signals = detect_market_signals(
        {"win_win": win_win, "draw": draw, "win_lose": win_lose},
        macau_ref,
        fundamentals_win_pct,
    )

    score_odds = base.get("score_odds", {})
    if isinstance(score_odds, str):
        try:
            score_odds = json.loads(score_odds)
        except (json.JSONDecodeError, TypeError):
            score_odds = {}

    half_full = base.get("half_full_odds", {})
    if isinstance(half_full, str):
        try:
            half_full = json.loads(half_full)
        except (json.JSONDecodeError, TypeError):
            half_full = {}

    return FusedOdds(
        win_win=max(1.05, win_win),
        draw=max(2.5, draw),
        win_lose=max(1.05, win_lose),
        handicap=str(macau_ref.get("handicap", base.get("handicap", "0"))),
        handicap_win=macau_ref.get("handicap_win", base.get("handicap_win", 1.9)),
        handicap_draw=macau_ref.get("handicap_draw", base.get("handicap_draw", 3.3)),
        handicap_lose=macau_ref.get("handicap_lose", base.get("handicap_lose", 1.9)),
        over_under=str(base.get("over_under", "2.5")),
        over_odds=base.get("over_odds", 1.9),
        under_odds=base.get("under_odds", 1.9),
        score_odds=score_odds,
        half_full_odds=half_full,
        imp_win=round(weighted_imp["imp_win"], 1),
        imp_draw=round(weighted_imp["imp_draw"], 1),
        imp_lose=round(weighted_imp["imp_lose"], 1),
        sources_used=sources,
        market_signals=signals,
    )


def score_distribution_from_odds(score_odds: dict) -> dict[str, float]:
    """Convert score odds dict to normalized probability distribution."""
    if not score_odds:
        return {}
    clean = {
        k: v for k, v in score_odds.items()
        if not str(k).startswith("_") and v and float(v) > 0 and ":" in str(k)
    }
    if not clean:
        return {}
    inv = {s: 1.0 / float(o) for s, o in clean.items()}
    for key, label in (("胜其它", "4:1"), ("win_other", "4:1")):
        o = score_odds.get(key)
        if o and float(o) > 1:
            inv[label] = inv.get(label, 0) + (1.0 / float(o)) * 0.65
    total = sum(inv.values())
    return {s: p / total for s, p in inv.items()}


def fused_odds_to_dict(fused: FusedOdds) -> dict:
    """Convert FusedOdds to plain dict for rule engine / DB."""
    return {
        "win_win": fused.win_win,
        "draw": fused.draw,
        "win_lose": fused.win_lose,
        "handicap": fused.handicap,
        "handicap_win": fused.handicap_win,
        "handicap_draw": fused.handicap_draw,
        "handicap_lose": fused.handicap_lose,
        "over_under": fused.over_under,
        "over_odds": fused.over_odds,
        "under_odds": fused.under_odds,
        "score_odds": fused.score_odds,
        "half_full_odds": fused.half_full_odds,
        "imp_win": fused.imp_win,
        "imp_draw": fused.imp_draw,
        "imp_lose": fused.imp_lose,
        "market_signals": fused.market_signals,
        "sources_used": fused.sources_used,
    }
