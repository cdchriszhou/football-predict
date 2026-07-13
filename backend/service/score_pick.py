"""CRS-anchored score selection — market-first with model/xG tie-breakers."""
from __future__ import annotations

from service.score_pick_config import (
    get_config,
    get,
    heavy_fav_sp_win,
    heavy_fav_sp_lose,
    draw_sp_cap,
    draw_rate_min,
    blowout_odd_gap_cap,
    is_heavy_fav_away,
    is_heavy_fav_home,
    is_strong_home_fav,
    draw_ratio_cap,
    draw_gap_cap,
    stage_draw_boost,
    get_config as _get_config,
)


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


def is_knockout_stage(stage: str | None) -> bool:
    return bool(stage and stage not in ("", "小组赛"))


def _poisson_score_ranking(
    expected_a: float,
    expected_b: float,
    draw_rate: float = 25.0,
) -> list[tuple[str, float]]:
    from service.rule_engine import RuleEngine
    return RuleEngine._score_probabilities(
        expected_a, expected_b, 0.0, draw_rate, 2.5,
    )


def _first_score_with_outcome(
    ranked: list[tuple[str, float]],
    outcome: str,
    *,
    exclude: set[str] | None = None,
) -> str | None:
    ex = exclude or set()
    for score, _ in ranked:
        if score in ex:
            continue
        if _score_outcome(score) == outcome:
            return score
    return None


def _knockout_favorite_primary(
    ranked: list[tuple[str, float]],
    margin: float,
    side: str,
) -> str | None:
    """Pick a realistic favourite win score (2:1 comeback-friendly, not only 0:0/1:1)."""
    if abs(margin) >= 1.5:
        prefs_home = ["2:0", "3:1", "2:1", "1:0", "3:0"]
        prefs_away = ["0:2", "1:3", "1:2", "0:1", "0:3"]
    else:
        prefs_home = ["2:1", "1:0", "2:0", "3:1", "1:2"]
        prefs_away = ["1:2", "0:1", "0:2", "1:3", "2:1"]
    prefs = prefs_home if side == "win" else prefs_away
    by_score = {s: p for s, p in ranked}
    for s in prefs:
        if s in by_score and _score_outcome(s) == side:
            return s
    return _first_score_with_outcome(ranked, side)


def _knockout_favorite_secondary(
    ranked: list[tuple[str, float]],
    primary: str,
    *,
    rank_gap: int,
    win_rate: float,
    lose_rate: float,
    draw_rate: float = 28.0,
    xg_gap: float = 0.0,
) -> str:
    """Heavy favourites cluster wins; ET draw only when matchup is genuinely tight."""
    heavy = (rank_gap >= 35) or (rank_gap >= 22 and max(win_rate, lose_rate) >= 58.0)
    if heavy:
        alt = _first_score_with_outcome(ranked, _score_outcome(primary), exclude={primary})
        if alt:
            return alt
        return "2:0" if _score_outcome(primary) == "win" else "0:2"
    tight = (
        rank_gap < 12
        and max(win_rate, lose_rate) < 55.0
        and draw_rate >= 30.0
        and xg_gap < 1.0
    )
    if tight:
        draw = _first_score_with_outcome(ranked, "draw")
        if draw and draw != primary:
            return draw
    alt = _first_score_with_outcome(ranked, _score_outcome(primary), exclude={primary})
    return alt or ("2:1" if _score_outcome(primary) == "win" else "1:2")


def finalize_knockout_score_picks(
    best_scores: list[str],
    *,
    expected_a: float,
    expected_b: float,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    rank_a: int | None = None,
    rank_b: int | None = None,
    stage: str | None = None,
) -> tuple[list[str], str | None]:
    """
    Without CRS odds, Poisson often tops with 1:1 in knockout — reorder by favourite strength.
    """
    if not is_knockout_stage(stage):
        picks = [s for s in (best_scores or []) if s and s != "?"][:2]
        return picks, None

    ranked = _poisson_score_ranking(expected_a, expected_b, draw_rate)
    if not ranked:
        picks = [s for s in (best_scores or []) if s and s != "?"][:2]
        return picks, None

    rank_gap = abs(int(rank_a or 50) - int(rank_b or 50))
    margin = expected_a - expected_b
    wdl_margin = abs(win_rate - lose_rate)
    fav_side = "win" if win_rate >= lose_rate + 3.0 else (
        "lose" if lose_rate >= win_rate + 3.0 else "draw"
    )

    fav_clear = fav_side in ("win", "lose") and (
        rank_gap >= 6 or wdl_margin >= 14.0
    )
    if fav_clear:
        primary = _knockout_favorite_primary(ranked, margin, fav_side)
        if not primary:
            primary = _first_score_with_outcome(ranked, fav_side) or ranked[0][0]
        secondary = _knockout_favorite_secondary(
            ranked, primary,
            rank_gap=rank_gap,
            win_rate=win_rate,
            lose_rate=lose_rate,
            draw_rate=draw_rate,
            xg_gap=abs(margin),
        )
        # Only keep draw secondary for genuinely tight knockout matchups
        if (
            rank_gap < 12
            and wdl_margin < 18
            and draw_rate >= 32.0
            and abs(margin) < 1.0
        ):
            draw_alt = _first_score_with_outcome(ranked, "draw", exclude={primary})
            if draw_alt and draw_alt != primary:
                secondary = draw_alt
        underdog = "lose" if fav_side == "win" else "win"
        underdog_prefs = (
            ["1:2", "2:1", "0:1", "2:2", "1:0"]
            if fav_side == "win"
            else ["2:1", "1:2", "1:0", "2:2", "0:1"]
        )
        by_score = {s for s, _ in ranked}
        upset = None
        for s in underdog_prefs:
            if s in by_score and _score_outcome(s) == underdog:
                upset = s
                break
        if not upset:
            upset = _first_score_with_outcome(ranked, underdog) or (
                "0:1" if fav_side == "win" else "1:0"
            )
        return [primary, secondary], upset

    primary = _first_score_with_outcome(ranked, "draw") or ranked[0][0]
    secondary = (
        _first_score_with_outcome(ranked, "win")
        or _first_score_with_outcome(ranked, "lose")
        or (best_scores[1] if len(best_scores or []) > 1 else "1:0")
    )
    upset = _first_score_with_outcome(
        ranked, "lose" if win_rate >= lose_rate else "win", exclude={primary, secondary},
    )
    return [primary, secondary], upset


def poisson_to_synthetic_crs(
    expected_a: float,
    expected_b: float,
    draw_rate: float = 25.0,
) -> dict[str, float]:
    """Implied CRS map from Poisson (for pipeline when bookmaker CRS missing)."""
    ranked = _poisson_score_ranking(expected_a, expected_b, draw_rate)
    if not ranked:
        return {}
    max_p = max(p for _, p in ranked) or 1e-9
    out: dict[str, float] = {}
    for score, prob in ranked:
        if ":" not in score:
            continue
        # Lower implied odd for higher probability; cap range for stability
        odd = max(4.0, min(35.0, 1.0 / max(prob / max_p, 0.02) * 3.5))
        out[score] = round(odd, 2)
    return out


def _effective_knockout_draw_rate(
    draw_rate: float,
    *,
    win_rate: float,
    lose_rate: float,
    sp_win: float | None = None,
    sp_draw: float | None = None,
    sp_lose: float | None = None,
) -> float:
    """Cap model draw for knockout synthetic CRS when market fav is clear."""
    dr = float(draw_rate)
    if sp_win and sp_draw and sp_lose:
        try:
            over = 1.0 / float(sp_win) + 1.0 / float(sp_draw) + 1.0 / float(sp_lose)
            market_draw = (1.0 / float(sp_draw)) / over * 100.0
            dr = min(dr, market_draw + 4.0)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    clear_fav = (sp_win is not None and sp_win < 1.60) or (sp_lose is not None and sp_lose < 1.60)
    if clear_fav:
        dr = min(dr, 28.0)
    if max(win_rate, lose_rate) >= 55.0 and abs(win_rate - lose_rate) >= 15.0:
        dr = min(dr, 26.0)
    return max(18.0, dr)


def build_knockout_synthetic_crs(
    expected_a: float,
    expected_b: float,
    *,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    sp_win: float | None = None,
    sp_draw: float | None = None,
    sp_lose: float | None = None,
) -> dict[str, float]:
    """Poisson CRS for knockout, anchored to market W/D/L when book CRS missing."""
    eff_dr = _effective_knockout_draw_rate(
        draw_rate,
        win_rate=win_rate,
        lose_rate=lose_rate,
        sp_win=sp_win,
        sp_draw=sp_draw,
        sp_lose=sp_lose,
    )
    out = poisson_to_synthetic_crs(expected_a, expected_b, eff_dr)
    if not out:
        return {}
    dom = "win" if win_rate >= lose_rate else "lose"
    for score in list(out.keys()):
        outcome = _score_outcome(score)
        try:
            odd = float(out[score])
        except (TypeError, ValueError):
            continue
        if outcome == dom:
            out[score] = round(odd * 0.88, 2)
        elif outcome == "draw":
            out[score] = round(odd * 1.18, 2)
    return out


def cap_knockout_wdl_to_market(
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    stage: str | None,
    *,
    sp_win: float | None = None,
    sp_draw: float | None = None,
    sp_lose: float | None = None,
) -> tuple[float, float, float]:
    """Pull inflated model draw toward market implied draw in knockout rounds."""
    if not is_knockout_stage(stage):
        return win_rate, draw_rate, lose_rate
    if not (sp_win and sp_draw and sp_lose):
        return win_rate, draw_rate, lose_rate
    try:
        over = 1.0 / float(sp_win) + 1.0 / float(sp_draw) + 1.0 / float(sp_lose)
        market_draw = (1.0 / float(sp_draw)) / over * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return win_rate, draw_rate, lose_rate
    if draw_rate <= market_draw + 10.0:
        return win_rate, draw_rate, lose_rate
    target_d = min(draw_rate, market_draw + 6.0)
    shift = draw_rate - target_d
    return _normalize_wdl(win_rate + shift / 2, target_d, lose_rate + shift / 2)


def prefer_close_crs_secondary(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    stage: str | None = None,
) -> list[str]:
    """Knockout only: same-outcome secondary prefers tighter CRS neighbor (2:1 over 3:1)."""
    if not is_knockout_stage(stage) or not best_scores or len(best_scores) < 2 or not score_odds:
        return best_scores
    primary, secondary = best_scores[0], best_scores[1]
    if _score_outcome(primary) != _score_outcome(secondary):
        return best_scores
    alt = _best_same_outcome_alternate(_rank_crs(score_odds, set()), primary, gap_cap=4.0)
    if not alt or alt == secondary:
        return best_scores
    try:
        sec_total = sum(map(int, secondary.split(":")))
        alt_total = sum(map(int, alt.split(":")))
    except ValueError:
        return best_scores
    if alt_total < sec_total:
        return [primary, alt]
    return best_scores


def prepare_pipeline_crs_and_hints(
    crs: dict[str, float] | None,
    *,
    expected_a: float,
    expected_b: float,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    model_scores: list[str] | None,
    stage: str | None,
    rank_a: int | None = None,
    rank_b: int | None = None,
    sp_win: float | None = None,
    sp_draw: float | None = None,
    sp_lose: float | None = None,
) -> tuple[dict[str, float], list[str], str | None]:
    """
    Normalize CRS input for run_full_score_pipeline.

    Knockout fixtures without bookmaker CRS get market-anchored Poisson synthetic
    odds after finalize_knockout_score_picks (same path as prediction_service).
    """
    hints = [s for s in (model_scores or []) if s and s != "?"]
    if crs:
        return crs, hints, None

    if not is_knockout_stage(stage):
        return {}, hints, None

    ko_scores, ko_upset = finalize_knockout_score_picks(
        hints,
        expected_a=expected_a,
        expected_b=expected_b,
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
        rank_a=rank_a,
        rank_b=rank_b,
        stage=stage,
    )
    hints = ko_scores or hints
    synthetic = build_knockout_synthetic_crs(
        expected_a,
        expected_b,
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
        sp_win=sp_win,
        sp_draw=sp_draw,
        sp_lose=sp_lose,
    )
    if synthetic:
        return synthetic, hints, ko_upset
    return {}, hints, ko_upset


def ensure_knockout_underdog_upset(
    best_scores: list[str],
    upset: str | None,
    *,
    win_rate: float,
    lose_rate: float,
    rank_a: int | None,
    rank_b: int | None,
    crs: dict[str, float],
    stage: str | None,
    sp_draw: float | None = None,
) -> str | None:
    """When favourite is clear, cold pick should be underdog win — not another draw."""
    if not is_knockout_stage(stage) or not best_scores:
        return upset
    rank_gap = abs(int(rank_a or 50) - int(rank_b or 50))
    wdl_margin = abs(win_rate - lose_rate)
    if rank_gap < 8 and wdl_margin < 12.0:
        return upset
    fav_home = win_rate >= lose_rate + 5.0
    fav_away = lose_rate >= win_rate + 5.0
    if not fav_home and not fav_away:
        return upset
    underdog_out = "lose" if fav_home else "win"
    pri_out = _score_outcome(best_scores[0])
    if pri_out == underdog_out:
        return upset
    if upset and _score_outcome(upset) == "draw":
        # Market prices knockout ET/draw (e.g. Germany–Paraguay draw @ 4.50)
        if sp_draw is not None and sp_draw >= 3.8:
            return upset
        if any(_score_outcome(s) == "draw" for s in best_scores):
            return upset
        heavy_fav = rank_gap >= 12 and max(win_rate, lose_rate) >= 62.0
        if not heavy_fav:
            return upset
    elif upset and _score_outcome(upset) != pri_out:
        return upset
    prefs = (
        ["1:2", "0:1", "0:2", "1:3", "2:3"]
        if underdog_out == "lose"
        else ["2:1", "1:0", "3:2", "2:0"]
    )
    listed = _listed_crs_scores(crs)
    for s in prefs:
        if s in listed and s not in best_scores:
            return s
    return _first_score_with_outcome(
        _rank_crs(crs, set(best_scores)),
        underdog_out,
        exclude=set(best_scores),
    ) or upset


def _listed_crs_scores(score_odds: dict | None) -> set[str]:
    return {str(k) for k in (score_odds or {}) if ":" in str(k)}


def score_matches_pick(
    actual: str,
    pick: str,
    score_odds: dict | None = None,
) -> bool:
    """True when actual result falls in the CRS pick bucket (incl. 胜/平/负其它)."""
    if not actual or not pick or pick == "?":
        return False
    if actual == pick:
        return True
    out = _score_outcome(actual)
    if pick == "胜其它":
        if out != "win":
            return False
        listed = _listed_crs_scores(score_odds)
        return actual not in listed if listed else True
    if pick == "平其它":
        return out == "draw" and actual not in _listed_crs_scores(score_odds)
    if pick == "负其它":
        if out != "lose":
            return False
        listed = _listed_crs_scores(score_odds)
        return actual not in listed if listed else True
    return False


def _has_crs_special(score_odds: dict, key: str) -> bool:
    try:
        v = (score_odds or {}).get(key)
        return v is not None and float(v) > 1.01
    except (TypeError, ValueError):
        return False


def _rank_crs(score_odds: dict, skip: set[str]) -> list[tuple[str, float]]:
    rows = []
    for k, v in (score_odds or {}).items():
        if str(k).startswith("_") or ":" not in str(k):
            continue
        try:
            odd = float(v)
        except (TypeError, ValueError):
            continue
        if odd <= 1.01 or k in skip:
            continue
        rows.append((str(k), odd))
    return sorted(rows, key=lambda x: x[1])


def _crs_map(ranked: list[tuple[str, float]]) -> dict[str, float]:
    return dict(ranked)


def _best_draw(ranked: list[tuple[str, float]], skip: set[str]) -> str | None:
    for score, _ in ranked:
        if score in skip:
            continue
        if _score_outcome(score) == "draw":
            return score
    return None


def _draw_close_to_primary(
    ranked: list[tuple[str, float]],
    primary: str,
    draw_pick: str,
    *,
    ratio_cap: float | None = None,
    gap_cap: float | None = None,
) -> bool:
    cfg = _get_config()
    ratio = ratio_cap if ratio_cap is not None else float(cfg.get("DRAW_RATIO_CAP", 1.55))
    gap = gap_cap if gap_cap is not None else float(cfg.get("DRAW_GAP_CAP", 2.0))
    cmap = _crs_map(ranked)
    pri_odd = cmap.get(primary)
    draw_odd = cmap.get(draw_pick)
    if not pri_odd or not draw_odd:
        return False
    return (draw_odd / pri_odd) <= ratio and (draw_odd - pri_odd) <= gap


def _best_home_win(
    ranked: list[tuple[str, float]],
    skip: set[str],
    *,
    expected_a: float = 1.0,
) -> str | None:
    """Pick best home-win CRS line; prefer 2:0 when close to 1:0 and xG supports it."""
    one_nil: tuple[float, str] | None = None
    two_nil: tuple[float, str] | None = None
    best: tuple[float, str] | None = None
    for score, odd in ranked:
        if score in skip:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if ga <= gb:
            continue
        if ga == 1 and gb == 0:
            one_nil = (odd, score)
        elif ga == 2 and gb == 0:
            two_nil = (odd, score)
        if best is None or odd < best[0]:
            best = (odd, score)
    if two_nil and one_nil and expected_a >= 1.0 and (two_nil[0] - one_nil[0]) <= 1.5:
        return two_nil[1]
    return best[1] if best else None


def _home_win_close_to_draw(
    ranked: list[tuple[str, float]],
    draw_pick: str,
    home_win: str,
    *,
    gap_cap: float = 4.0,
) -> bool:
    cmap = _crs_map(ranked)
    d_odd = cmap.get(draw_pick)
    h_odd = cmap.get(home_win)
    if not d_odd or not h_odd:
        return False
    return (h_odd - d_odd) <= gap_cap


def _is_heavy_fav_away(lose_rate: float, sp_lose: float | None) -> bool:
    return is_heavy_fav_away(lose_rate, sp_lose)


def _is_heavy_fav_home(win_rate: float, sp_win: float | None) -> bool:
    return is_heavy_fav_home(win_rate, sp_win)


def _is_strong_home_fav(win_rate: float, sp_win: float | None) -> bool:
    """Stricter bar for blowout / 胜其它 upset paths — avoids moderate favs like Iran 1.59."""
    return is_strong_home_fav(win_rate, sp_win)


def _is_competitive(win_rate: float, lose_rate: float, draw_rate: float) -> bool:
    cfg = _get_config()
    gap = float(cfg.get("COMPETITIVE_WIN_GAP", 28.0))
    dr_min = float(cfg.get("COMPETITIVE_DRAW_MIN", 18.0))
    return abs(win_rate - lose_rate) < gap and draw_rate >= dr_min


def _market_fav_a(sp_win: float | None, sp_lose: float | None) -> bool | None:
    if sp_win and sp_lose and sp_win > 0 and sp_lose > 0:
        return sp_win < sp_lose
    return None


def _should_promote_draw_to_primary(
    ranked: list[tuple[str, float]],
    primary: str,
    draw_pick: str,
    *,
    draw_rate: float,
    pri_out: str,
    sp_win: float | None = None,
    sp_draw: float | None = None,
) -> bool:
    """Only promote draw over a win/loss CRS primary when market supports a draw."""
    cfg = _get_config()
    if pri_out == "draw" or not draw_pick:
        return False
    hf_sp_win = float(cfg.get("HEAVY_FAV_SP_WIN", 1.55))
    ds_cap = float(cfg.get("DRAW_SP_CAP", 3.7))
    dr_min = float(cfg.get("DRAW_RATE_MIN", 26.0))
    if sp_win is not None and sp_win < hf_sp_win:
        return False
    if sp_draw is not None and sp_draw > ds_cap:
        return False
    if draw_rate < dr_min:
        return False
    cmap = _crs_map(ranked)
    if cmap.get(primary) == cmap.get(draw_pick):
        return False
    return _draw_close_to_primary(ranked, primary, draw_pick)


def _parse_handicap_line(handicap: str | None) -> float:
    if not handicap:
        return 0.0
    try:
        return float(str(handicap).replace("+", ""))
    except ValueError:
        return 0.0


def _blowout_odd_gap_cap(
    sp_win: float | None,
    *,
    expected_a: float = 1.2,
    handicap: str | None = None,
) -> float:
    """Max CRS odd gap from anchor when promoting rout scorelines."""
    cfg = _get_config()
    default_gap = float(cfg.get("BLOWOUT_ODD_GAP_DEFAULT", 5.0))
    gap_sp_125 = float(cfg.get("BLOWOUT_ODD_GAP_SP_125", 8.0))
    gap_sp_145 = float(cfg.get("BLOWOUT_ODD_GAP_SP_145", 6.5))
    gap_sp_165 = float(cfg.get("BLOWOUT_ODD_GAP_SP_165", 5.0))

    if sp_win is None:
        cap = default_gap
    elif sp_win < 1.25:
        cap = gap_sp_125
    elif sp_win < 1.45:
        cap = gap_sp_145
    elif sp_win < 1.65:
        cap = gap_sp_165
    else:
        cap = default_gap
    if expected_a >= 2.0 and _parse_handicap_line(handicap) <= -1:
        cap = max(cap, 14.0)
    return cap


def _blowout_tiers(*, high_tiers_only: bool) -> list[tuple[str, float, float | None]]:
    """Shutout-first tiers for deep-favourite rout promotion."""
    cfg = _get_config()
    tiers_cfg = cfg.get("BLOWOUT_TIERS", [
        ("4:0", 1.75, 1.35),
        ("3:0", 1.50, 1.55),
        ("5:0", 2.00, 1.25),
        ("4:1", 1.85, 1.55),
        ("3:1", 1.65, 1.50),
    ])
    tiers_high_only = cfg.get("BLOWOUT_TIERS_HIGH_ONLY", [
        ("4:0", 1.75, 1.35),
        ("3:0", 1.50, 1.55),
        ("5:0", 2.00, 1.25),
        ("4:1", 1.85, 1.55),
    ])
    if high_tiers_only:
        return [tuple(t) for t in tiers_high_only]
    return [tuple(t) for t in tiers_cfg]


def apply_favourite_blowout_scores(
    best_scores: list[str],
    score_odds: dict | None,
    *,
    sp_win: float | None = None,
    handicap: str | None = None,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
    expected_a: float = 1.2,
    high_tiers_only: bool = False,
    resilience: dict | None = None,
) -> list[str]:
    """Deep favourite with -handicap: promote 3:0/4:0 when CRS anchor is a modest home win."""
    if not best_scores or not score_odds or sp_win is None:
        return best_scores
    from service.score_context import _resilience_blocks_blowout
    if _resilience_blocks_blowout(resilience or {}):
        return best_scores
    ranked = _rank_crs(score_odds, set())
    crs_map = _crs_map(ranked)
    primary = best_scores[0]
    pri_odd = crs_map.get(primary)
    odd_gap_cap = _blowout_odd_gap_cap(sp_win, expected_a=expected_a, handicap=handicap)
    tiers = _blowout_tiers(high_tiers_only=high_tiers_only)

    def _effective_max_sp(high: str, max_sp: float | None) -> float | None:
        if max_sp is None:
            return None
        eff = max_sp
        if high in ("4:0", "5:0") and expected_a >= 2.0:
            eff = max(eff, 1.82)
        if high == "4:1" and expected_a >= 2.0:
            eff = max(eff, 1.85)
        return eff

    def _tier_ok(high: str, min_xg: float, max_sp: float | None) -> bool:
        eff_max = _effective_max_sp(high, max_sp)
        if eff_max is not None and sp_win >= eff_max:
            return False
        if high not in crs_map:
            return False
        if primary not in ("2:1", "2:0", "1:0", "3:1", "3:0", "4:1", "4:0"):
            return False
        if expected_a < min_xg:
            return False
        high_odd = crs_map[high]
        if pri_odd is not None and high_odd > pri_odd + odd_gap_cap:
            return False
        return True

    if len(best_scores) > 1 and _score_outcome(best_scores[1]) == "draw":
        if sp_win < 1.75 and primary in crs_map:
            for high, min_xg, max_sp in tiers:
                if _tier_ok(high, min_xg, max_sp):
                    return [high, best_scores[1]]
            return best_scores
    if sp_win >= 1.80 and win_rate < 58.0:
        return best_scores
    hcp = _parse_handicap_line(handicap)
    if sp_win >= 1.90 or hcp > -0.5 or win_rate < 48.0:
        return best_scores
    if primary not in crs_map:
        return best_scores
    for high, min_xg, max_sp in tiers:
        if _tier_ok(high, min_xg, max_sp):
            sec = best_scores[1] if len(best_scores) > 1 else primary
            if sec == high:
                sec = primary
            return [high, sec]
    return best_scores


def _is_low_scoring_win_cluster(
    ranked: list[tuple[str, float]],
    *,
    sp_draw: float | None = None,
) -> bool:
    """CRS tops 1:0 with tight 1:1 — market expects narrow win (Morocco 1:0, Paraguay 1:0)."""
    if not ranked or ranked[0][0] != "1:0":
        return False
    cmap = _crs_map(ranked)
    one_nil = cmap.get("1:0")
    one_one = cmap.get("1:1")
    two_zero = cmap.get("2:0")
    if one_nil is None:
        return False
    if one_one is not None:
        gap = one_one - one_nil
        if gap <= 0:
            return False
        if gap <= 0.8:
            return True
        if sp_draw is not None and sp_draw <= 3.35 and gap <= 1.5:
            return True
    if (
        sp_draw is not None
        and sp_draw >= 3.5
        and two_zero is not None
        and (two_zero - one_nil) <= 1.0
    ):
        return True
    return False


def _is_protected_likely_pair(best_scores: list[str]) -> bool:
    """Likely pairs that later cluster steps must not overwrite."""
    if len(best_scores) < 2:
        return False
    sec = best_scores[1]
    if sec == "0:0":
        return True
    try:
        ga, gb = map(int, sec.split(":"))
    except ValueError:
        return False
    if ga >= 4 and ga > gb:
        return True
    return ga >= 3 and gb == 0


def preserve_one_nil_cluster(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    sp_draw: float | None = None,
) -> list[str]:
    """Keep 1:0 + 1:1 when CRS cluster signals a low-scoring favourite win."""
    if not best_scores or not score_odds:
        return best_scores
    if _is_protected_likely_pair(best_scores):
        return best_scores
    ranked = _rank_crs(score_odds, set())
    if not _is_low_scoring_win_cluster(ranked, sp_draw=sp_draw):
        return best_scores
    cmap = _crs_map(ranked)
    secondary = "1:1" if cmap.get("1:1") else best_scores[1] if len(best_scores) > 1 else None
    if secondary:
        return ["1:0", secondary]
    return ["1:0"]


def promote_strong_home_multi_goal(
    best_scores: list[str],
    score_odds: dict | None,
    *,
    sp_win: float | None = None,
    sp_draw: float | None = None,
    win_rate: float = 50.0,
) -> list[str]:
    """SPF home fav <1.70: upgrade 1:0 anchor to nearby 2:0/2:1/3:0 CRS lines."""
    if not best_scores or not score_odds or sp_win is None or sp_win >= 1.70:
        return best_scores
    ranked = _rank_crs(score_odds, set())
    if _is_low_scoring_win_cluster(ranked, sp_draw=sp_draw):
        return best_scores
    cmap = _crs_map(ranked)
    primary = best_scores[0]
    if _score_outcome(primary) == "draw":
        return best_scores
    pri_odd = cmap.get(primary)
    if not pri_odd:
        return best_scores
    try:
        pga, pgb = map(int, primary.split(":"))
    except ValueError:
        pga, pgb = 0, 0
    if pga >= 3 or (pga >= 2 and pgb >= 1):
        return best_scores
    odd_cap = _blowout_odd_gap_cap(sp_win) if sp_win < 1.45 and win_rate >= 58.0 else 1.2
    candidates = ("3:0", "2:0", "2:1") if sp_win < 1.45 and win_rate >= 58.0 else ("2:0", "2:1", "3:0")
    for score in candidates:
        odd = cmap.get(score)
        if odd is None or odd - pri_odd > odd_cap:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if ga > gb:
            secondary = best_scores[1] if len(best_scores) > 1 and best_scores[1] != score else primary
            if secondary == score:
                secondary = primary
            return [score, secondary]
    return best_scores


def promote_extreme_home_favourite(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    sp_win: float | None = None,
    handicap: str | None = None,
    win_rate: float = 50.0,
) -> list[str]:
    """Ultra-deep home fav (co-host rout): pair CRS top shutout with 4:0/5:0/6:0 line."""
    if not best_scores or not score_odds or sp_win is None:
        return best_scores
    if sp_win >= 1.25 or win_rate < 70.0:
        return best_scores
    if _parse_handicap_line(handicap) > -2:
        return best_scores
    ranked = _rank_crs(score_odds, set())
    shutouts: list[str] = []
    for score, odd in ranked[:14]:
        if odd > 22.0:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if ga > gb and gb == 0:
            shutouts.append(score)
    if len(shutouts) < 2:
        return best_scores
    high = shutouts[-1]
    try:
        if int(high.split(":")[0]) < 4:
            return best_scores
    except ValueError:
        return best_scores
    return [shutouts[0], high]


def boost_heavy_favorite_scores(
    best_scores: list[str],
    score_odds: dict | None,
    *,
    win_rate: float,
    handicap: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
    resilience: dict | None = None,
) -> list[str]:
    """For extreme favourites (deep handicap / huge rank gap), add high-score CRS lines."""
    if not best_scores or not score_odds:
        return best_scores
    sig = resilience or {}
    if sig.get("opponent_clean_sheet") or (
        sig.get("favorite_scoring_drought") and sig.get("opponent_defensive")
    ):
        return best_scores
    gap = abs(int(rank_a or 50) - int(rank_b or 50))
    hcp = _parse_handicap_line(handicap)
    ranked = _rank_crs(score_odds, set())
    cmap = _crs_map(ranked)
    primary = best_scores[0]
    secondary = best_scores[1] if len(best_scores) > 1 else None
    win_other: str | None = "胜其它" if _has_crs_special(score_odds, "胜其它") else None

    boost: str | None = None
    if gap >= 50 and win_rate >= 70.0:
        five_nil: str | None = None
        multi_goal: str | None = None
        for score, _ in ranked:
            if ":" not in score:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga > gb:
                if ga == 5 and gb == 0:
                    five_nil = score
                elif ga >= 4 and gb <= 1 and multi_goal is None:
                    multi_goal = score
        boost = five_nil or multi_goal or win_other
    elif gap >= 25 and win_rate >= 58.0 and _score_outcome(primary) == "win":
        for score, _ in ranked:
            if score == primary or ":" not in score:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga > gb and ga >= 3 and gb <= 1:
                boost = score
                break
        if not boost and win_other:
            boost = win_other
    elif hcp <= -2 and win_rate >= 75.0:
        # Deep handicap but moderate rank gap: follow CRS rank (3:0 before 4:0)
        for score, _ in ranked:
            if score == primary:
                continue
            if ":" not in score:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga > gb and ga >= 2 and gb <= 1:
                boost = score
                break
    else:
        return best_scores

    if not boost or boost == primary:
        return best_scores[:2]
    if secondary and _score_outcome(secondary) == "draw":
        return [primary, secondary]
    if boost == secondary:
        return [primary, secondary]
    if hcp <= -2 and win_rate >= 75.0 and gap < 50 and secondary and secondary in cmap:
        sec_odd = cmap[secondary]
        boost_odd = cmap.get(boost, 99.0)
        if boost_odd > sec_odd + 1.0:
            return best_scores[:2]
    return [primary, boost][:2]


def _crs_secondary_different_outcome(
    ranked: list[tuple[str, float]],
    primary: str,
    pri_out: str,
) -> str | None:
    """CRS rank-2+ line with a different W/D/L outcome than primary."""
    for score, _ in ranked[1:]:
        if score == primary:
            continue
        if _score_outcome(score) != pri_out:
            return score
    return None


def _best_same_outcome_alternate(
    ranked: list[tuple[str, float]],
    primary: str,
    *,
    gap_cap: float = 5.0,
    max_rank: int = 12,
) -> str | None:
    """Another CRS line with same W/D/L as primary, within odds gap (e.g. 2:0 → 2:1/3:1)."""
    pri_out = _score_outcome(primary)
    cmap = _crs_map(ranked)
    pri_odd = cmap.get(primary)
    if pri_odd is None:
        return None
    try:
        pga, pgb = map(int, primary.split(":"))
    except ValueError:
        pga, pgb = 0, 0
    candidates: list[tuple[float, int, str]] = []
    concession: list[tuple[int, float, str]] = []
    for score, odd in ranked[1:max_rank]:
        if score == primary or _score_outcome(score) != pri_out:
            continue
        if (odd - pri_odd) > gap_cap:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        total = ga + gb
        if pga >= 2 and pgb == 0 and ga > gb:
            if gb >= 1:
                concession.append((ga, gb, odd, score))
            elif ga >= 3:
                concession.append((ga, gb, odd, score))
        if pgb >= 2 and pga == 0 and gb > ga:
            concession.append((gb, ga, odd, score))
        goal_bonus = 0
        if pga >= 2 and pgb == 0 and ga >= 2 and total >= 3:
            goal_bonus = -2
        elif pga >= 2 and pgb == 0 and ga == 1 and gb == 0:
            goal_bonus = 2
        candidates.append((odd + goal_bonus, -total, score))
    if (pga >= 2 and pgb == 0 or pgb >= 2 and pga == 0) and concession:
        concession.sort(key=lambda x: (x[2], -x[0], -x[1]))
        return concession[0][3]
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _is_shutout_score(score: str, side: str) -> bool:
    """True when score is a shutout for side ('home' keeps ga=0, 'away' keeps gb=0)."""
    try:
        ga, gb = map(int, score.split(":"))
    except ValueError:
        return False
    if side == "home":
        return ga > gb and gb == 0
    return gb > ga and ga == 0


def _best_home_scoring_away_win(
    ranked: list[tuple[str, float]],
    *,
    exclude: set[str],
    max_odd: float = 16.0,
    lose_rate: float = 50.0,
) -> str | None:
    """Away-win CRS lines where the home side scores (1:2, 1:3 …)."""
    hits: list[tuple[float, str]] = []
    for score, odd in ranked:
        if score in exclude or odd > max_odd:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if ga >= 1 and gb > ga:
            hits.append((odd, score))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0])
    if lose_rate >= 62.0 and len(hits) >= 2 and (hits[1][0] - hits[0][0]) <= 2.5:
        return hits[1][1]
    return hits[0][1]


def refine_favorite_score_cluster(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    win_rate: float,
    lose_rate: float,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    resilience: dict | None = None,
) -> list[str]:
    """
    When favourite is clear, replace weak secondaries:
    - draw (1:1) → cluster alternate (2:1/3:0 home; 1:2/1:3 away)
    - shutout pair (0:2+0:3) → 0:2+1:2/1:3 (home concedes but still loses)
    """
    if not best_scores or not score_odds or len(best_scores) < 2:
        return best_scores
    if _is_protected_likely_pair(best_scores):
        return best_scores
    sig = resilience or {}
    if sig.get("opponent_clean_sheet") or (
        sig.get("favorite_scoring_drought") and sig.get("opponent_defensive")
    ):
        if _score_outcome(best_scores[1]) == "draw":
            return best_scores
    ranked = _rank_crs(score_odds, set())
    if not ranked:
        return best_scores
    primary, secondary = best_scores[0], best_scores[1]
    pri_out = _score_outcome(primary)
    sec_out = _score_outcome(secondary)
    home_fav = (
        pri_out == "win"
        and (win_rate >= 54.0 or (sp_win is not None and sp_win < 1.68))
    )
    away_fav = (
        pri_out == "lose"
        and (lose_rate >= 54.0 or (sp_lose is not None and sp_lose < 1.68))
    )

    if away_fav and secondary == "0:0":
        return best_scores

    if pri_out == sec_out and (home_fav or away_fav):
        if away_fav and _is_shutout_score(primary, "away") and _is_shutout_score(secondary, "away"):
            alt = _best_home_scoring_away_win(
                ranked, exclude={primary, secondary}, lose_rate=lose_rate,
            )
            if alt:
                return [primary, alt]

        if home_fav and _is_shutout_score(primary, "home") and _is_shutout_score(secondary, "home"):
            alt = _best_same_outcome_alternate(ranked, primary, gap_cap=5.0)
            if alt:
                try:
                    _, agb = map(int, alt.split(":"))
                except ValueError:
                    agb = 0
                if agb >= 1:
                    return [primary, alt]

    if sec_out == "draw":
        if not home_fav and not away_fav:
            return best_scores
        if away_fav and pri_out == "lose":
            alt = _best_home_scoring_away_win(
                ranked, exclude={primary, secondary}, lose_rate=lose_rate,
            )
            if alt:
                return [primary, alt]
        alt = _best_same_outcome_alternate(ranked, primary, gap_cap=4.5)
        if alt and away_fav and _is_shutout_score(alt, "away"):
            alt = _best_home_scoring_away_win(
                ranked, exclude={primary, secondary, alt}, lose_rate=lose_rate,
            )
        if alt:
            return [primary, alt]
        return best_scores

    if primary == "1:0" and pri_out == "win" and home_fav:
        cmap = _crs_map(ranked)
        if cmap.get("1:1") and secondary not in ("1:1", "2:0"):
            return [primary, "1:1"]

    return best_scores


def promote_open_game_high_score(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    expected_a: float = 1.2,
    expected_b: float = 1.0,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
) -> list[str]:
    """High xG, balanced fav: add 3:2/4:2-style secondary instead of low-total 2:0."""
    if not best_scores or not score_odds or len(best_scores) < 2:
        return best_scores
    total_xg = expected_a + expected_b
    both_can_score = expected_a >= 1.75 and expected_b >= 1.75
    spread = abs(win_rate - lose_rate)
    if total_xg < 4.0:
        return best_scores
    if not both_can_score and spread >= 28.0:
        return best_scores
    ranked = _rank_crs(score_odds, set())
    cmap = _crs_map(ranked)
    primary = best_scores[0]
    pri_odd = cmap.get(primary)
    if pri_odd is None:
        return best_scores
    try:
        ga, gb = map(int, primary.split(":"))
    except ValueError:
        return best_scores
    if ga == gb:
        return best_scores
    pri_out = _score_outcome(primary)
    gap_cap = 12.0 if total_xg >= 4.4 else 8.0
    best_alt: tuple[int, float, str] | None = None
    for score, odd in ranked[1:16]:
        if score == primary or _score_outcome(score) != pri_out:
            continue
        if (odd - pri_odd) > gap_cap:
            continue
        try:
            sga, sgb = map(int, score.split(":"))
        except ValueError:
            continue
        if sga + sgb >= ga + gb + 1:
            cand = (sga + sgb, odd, score)
            if best_alt is None or cand[0] > best_alt[0] or (cand[0] == best_alt[0] and cand[1] < best_alt[1]):
                best_alt = cand
    if best_alt:
        return [primary, best_alt[2]]
    return best_scores


def promote_knockout_blowout_scores(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    expected_a: float = 1.2,
    expected_b: float = 1.0,
    stage: str | None = None,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
    rank_gap: int = 0,
) -> list[str]:
    """Knockout: when xG/rank gap implies rout, promote 2:0+ over draw cluster."""
    if not is_knockout_stage(stage) or not best_scores or not score_odds:
        return best_scores
    xg_gap = abs(expected_a - expected_b)
    if xg_gap < 1.5 and rank_gap < 25:
        return best_scores
    ranked = _rank_crs(score_odds, set())
    if not ranked:
        return best_scores
    cmap = _crs_map(ranked)
    fav_side = "win" if expected_a >= expected_b else "lose"
    if fav_side == "win" and win_rate + 5 < lose_rate:
        fav_side = "lose"
    elif fav_side == "lose" and lose_rate + 5 < win_rate:
        fav_side = "win"
    prefs = (
        ["3:0", "2:0", "3:1", "2:1", "4:0"]
        if fav_side == "win"
        else ["0:3", "0:2", "1:3", "1:2", "0:4"]
    )
    primary = best_scores[0]
    pri_out = _score_outcome(primary)
    if pri_out == fav_side:
        return best_scores
    for score in prefs:
        if score not in cmap or _score_outcome(score) != fav_side:
            continue
        secondary = best_scores[1] if len(best_scores) > 1 else score
        if _score_outcome(secondary) == fav_side:
            return [score, secondary]
        alt = _best_same_outcome_alternate(ranked, score, gap_cap=6.0)
        return [score, alt or secondary]
    return best_scores


def promote_narrow_home_win_over_draw(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
) -> list[str]:
    """Tight CRS draw cluster + slight home lean → 1:0 over 1:1 as primary."""
    if not best_scores or len(best_scores) < 2 or not score_odds:
        return best_scores
    if best_scores[0] != "1:1" or best_scores[1] != "1:0":
        return best_scores
    if win_rate <= lose_rate + 2.0:
        return best_scores
    if (win_rate - lose_rate) > 10.0:
        return best_scores
    cmap = _crs_map(_rank_crs(score_odds, set()))
    d_odd = cmap.get("1:1")
    h_odd = cmap.get("1:0")
    if d_odd is None or h_odd is None or (h_odd - d_odd) > 1.2:
        return best_scores
    return ["1:0", "1:1"]


def _stage_draw_promotion_boost(stage: str | None) -> float:
    """Extra draw weight for CRS draw-promotion rules only (not global W/D/L)."""
    from service.score_pick_config import stage_draw_boost
    return stage_draw_boost(stage)


def prefer_poisson_primary_when_close(
    best_scores: list[str],
    model_scores: list[str] | None,
    score_odds: dict[str, float],
    *,
    odd_gap_cap: float = 1.0,
) -> list[str]:
    """Same W/D/L outcome: prefer Poisson top-1 when CRS odds are within gap."""
    if not best_scores or not model_scores or not score_odds:
        return best_scores
    primary = best_scores[0]
    poisson_top = next((s for s in model_scores if s and s != "?"), None)
    if not poisson_top or poisson_top == primary:
        return best_scores
    if _score_outcome(primary) != _score_outcome(poisson_top):
        return best_scores
    cmap = _crs_map(_rank_crs(score_odds, set()))
    pri_odd = cmap.get(primary)
    po_odd = cmap.get(poisson_top)
    if pri_odd is None or po_odd is None:
        return best_scores
    if (po_odd - pri_odd) > odd_gap_cap:
        return best_scores
    secondary = best_scores[1] if len(best_scores) > 1 and best_scores[1] != poisson_top else primary
    return [poisson_top, secondary]


def _upset_from_different_outcome(
    ranked: list[tuple[str, float]],
    exclude: set[str],
    *,
    primary_outcome: str,
) -> str | None:
    """Pick draw or underdog win when likely picks already share the favourite outcome."""
    covered = {_score_outcome(s) for s in exclude if s and ":" in str(s)}

    for target in ("draw", "lose", "win"):
        if target in covered:
            continue
        if target == "draw":
            draw_pick = _best_draw(ranked, exclude)
            if draw_pick:
                return draw_pick
            continue
        for score, odd in ranked:
            if score in exclude:
                continue
            if _score_outcome(score) == target and odd <= 14.0:
                return score

    draw_pick = _best_draw(ranked, exclude)
    if draw_pick:
        return draw_pick
    underdog = "lose" if primary_outcome == "win" else "win"
    for score, odd in ranked:
        if score in exclude:
            continue
        if _score_outcome(score) == underdog and odd <= 14.0:
            return score
    return None


def dominant_wdl_outcome(win_rate: float, draw_rate: float, lose_rate: float) -> str:
    """Return the leading W/D/L bucket from fused percentages."""
    if draw_rate >= win_rate and draw_rate >= lose_rate:
        return "draw"
    if win_rate >= lose_rate:
        return "win"
    return "lose"


def wdl_outcome_margin(win_rate: float, draw_rate: float, lose_rate: float) -> tuple[str, float]:
    rates = {"win": win_rate, "draw": draw_rate, "lose": lose_rate}
    dom = dominant_wdl_outcome(win_rate, draw_rate, lose_rate)
    others = [v for k, v in rates.items() if k != dom]
    return dom, rates[dom] - max(others) if others else 0.0


def _best_crs_for_outcome(
    ranked: list[tuple[str, float]],
    crs: dict[str, float],
    outcome: str,
    exclude: set[str],
    model_scores: list[str] | None = None,
) -> str | None:
    for ms in model_scores or []:
        if ms and ms not in exclude and ms in crs and _score_outcome(ms) == outcome:
            return ms
    for score, _ in ranked:
        if score not in exclude and _score_outcome(score) == outcome:
            return score
    return None


def _best_side_outcome_moderate(
    ranked: list[tuple[str, float]],
    outcome: str,
    exclude: set[str],
) -> str | None:
    """Prefer one-goal margin scores (0:1 / 1:0) over blowouts when filling secondary."""
    candidates: list[tuple[int, float, int, str]] = []
    for score, odd in ranked:
        if score in exclude or _score_outcome(score) != outcome:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        candidates.append((abs(ga - gb), odd, ga + gb, score))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    return candidates[0][3]


def align_score_picks_to_wdl(
    best_scores: list[str],
    crs: dict[str, float] | None,
    *,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    model_scores: list[str] | None = None,
    min_margin: float | None = None,
    resilience: dict | None = None,
    group_context: dict | None = None,
) -> list[str]:
    """Ensure likely scorelines match the fused W/D/L favourite (AI + market)."""
    from service.score_context import resilience_preserves_draw

    cfg = _get_config()
    margin_threshold = float(min_margin or cfg.get("ALIGN_MIN_MARGIN", 6.0))
    margin_strong = float(cfg.get("ALIGN_MARGIN_STRONG", 8.0))
    draw_preserve_rate = float(cfg.get("ALIGN_DRAW_PRESERVE_RATE", 20.0))
    same_dir_gap = float(cfg.get("ALIGN_SAME_DIR_GAP_CAP", 8.0))

    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    if not picks or not crs:
        return picks
    ctx = group_context or {}
    dom, margin = wdl_outcome_margin(win_rate, draw_rate, lose_rate)
    preserve_draw = resilience_preserves_draw(resilience or {}, draw_rate)
    # MD3 must-win: contextual picks override inflated draw W/D/L (Switzerland 2:1 Canada)
    if ctx.get("matchday") == 3 and ctx.get("stage") == "小组赛":
        pri = _score_outcome(picks[0])
        if ctx.get("both_must_win") and pri in ("win", "lose"):
            return picks
        if ctx.get("must_win_a") and pri == "win" and dom == "draw":
            return picks
        if ctx.get("must_win_b") and pri == "lose" and dom == "draw":
            return picks
        if ctx.get("must_win_a") and ctx.get("draw_suits_b") and pri == "win":
            return picks
        if ctx.get("must_win_b") and ctx.get("draw_suits_a") and pri == "lose":
            return picks
        # Qualified favourite vs desperate opponent — keep away rout (Tunisia 0:3 Netherlands)
        if ctx.get("qualified_b") and ctx.get("must_win_a") and pri == "lose":
            return picks
        if ctx.get("qualified_a") and ctx.get("must_win_b") and pri == "win":
            return picks
        # Rank + deep handicap imply away fav: keep rout (Curacao +2 vs Côte d'Ivoire)
        rank_gap = int(ctx.get("rank_gap") or 0)
        ra = int(ctx.get("rank_a") or 50)
        rb = int(ctx.get("rank_b") or 50)
        hcp = _parse_handicap_line(ctx.get("handicap"))
        if (
            rank_gap >= 30
            and rb + 25 <= ra
            and hcp >= 1.5
            and pri == "lose"
            and dom == "win"
        ):
            return picks
    force_align = False
    pri = _score_outcome(picks[0]) if picks else None
    if ctx.get("matchday") == 3 and ctx.get("stage") == "小组赛":
        if ctx.get("must_win_b") and lose_rate >= win_rate + 2 and pri in ("win", "draw"):
            dom = "lose"
            force_align = True
            margin = max(margin, margin_threshold)
        elif ctx.get("must_win_a") and win_rate >= lose_rate + 2 and pri in ("lose", "draw"):
            dom = "win"
            force_align = True
            margin = max(margin, margin_threshold)
    if margin < margin_threshold and not force_align:
        return picks
    ranked = _rank_crs(crs, set())
    if ranked and not force_align and margin < 8.0:
        crs_dom = _score_outcome(ranked[0][0])
        pri_dom = _score_outcome(picks[0]) if picks else None
        if crs_dom != dom and pri_dom == crs_dom:
            return picks

    if _score_outcome(picks[0]) != dom:
        primary = _best_crs_for_outcome(ranked, crs, dom, set(), model_scores)
        if primary:
            picks[0] = primary

    if len(picks) < 2:
        sec = _best_crs_for_outcome(ranked, crs, dom, {picks[0]}, model_scores)
        if sec:
            picks.append(sec)
    elif margin >= margin_strong and _score_outcome(picks[1]) != dom:
        # Keep draw secondary when R1 form / high draw_rate warns against forcing win-win pair
        if preserve_draw and _score_outcome(picks[1]) == "draw" and draw_rate >= draw_preserve_rate:
            pass
        else:
            sec = _best_crs_for_outcome(ranked, crs, dom, {picks[0]}, model_scores)
            if not sec and dom == "draw":
                alt_out = "lose" if lose_rate >= win_rate else "win"
                sec = _best_side_outcome_moderate(ranked, alt_out, {picks[0]})
            if not sec and dom == "win" and draw_rate >= draw_preserve_rate:
                sec = _best_crs_for_outcome(ranked, crs, "draw", {picks[0]}, model_scores)
            elif not sec and dom == "lose" and draw_rate >= draw_preserve_rate:
                sec = _best_crs_for_outcome(ranked, crs, "draw", {picks[0]}, model_scores)
            elif not sec and dom in ("win", "lose"):
                alt_out = "lose" if dom == "win" else "win"
                sec = _best_side_outcome_moderate(ranked, alt_out, {picks[0]})
            if sec:
                picks[1] = sec

    return picks[:2]


def _fix_same_direction_false_upset(
    picks: list[str],
    upset: str | None,
    crs: dict[str, float],
) -> str | None:
    """Reject upset lines that share the same W/D/L as the primary likely pick."""
    _, fixed_upset = reconcile_likely_upset_cluster(picks, upset, crs)
    return fixed_upset


def reconcile_likely_upset_cluster(
    picks: list[str],
    upset: str | None,
    crs: dict[str, float],
) -> tuple[list[str], str | None]:
    """
    Fix cluster mislabelling: upset must differ in W/D/L from the favourite pick,
    and must not be CRS-favoured over the secondary likely line (e.g. 3:0 cold vs 4:0 hot).
    """
    out = [s for s in (picks or []) if s and s != "?"][:2]
    upset_val = upset if upset and upset != "?" else None
    if not crs or not out:
        return out, upset_val

    pri_out = _score_outcome(out[0])
    if not pri_out or not upset_val or upset_val in ("胜其它", "平其它", "负其它"):
        return out, upset_val
    upset_out = _score_outcome(upset_val)

    # Draw upset (e.g. 0:0) with win primary + different draw secondary (1:1) is valid
    if upset_out != pri_out:
        if len(out) < 2 or upset_val != out[1]:
            return out, upset_val

    try:
        u_odd = float(crs[upset_val])
    except (TypeError, ValueError, KeyError):
        u_odd = None
    sec_odd = None
    same_dir_picks = [p for p in out if _score_outcome(p) == upset_out]
    if len(same_dir_picks) > 1:
        try:
            sec_odd = float(crs[same_dir_picks[1]])
        except (TypeError, ValueError, KeyError):
            sec_odd = None
    elif upset_out == pri_out and len(out) > 1:
        try:
            sec_odd = float(crs[out[1]])
        except (TypeError, ValueError, KeyError):
            sec_odd = None

    if u_odd is not None and upset_out == pri_out and (sec_odd is None or u_odd <= sec_odd + 0.05):
        exclude = set(out) | {upset_val}
        cfg = _get_config()
        same_dir_gap = float(cfg.get("ALIGN_SAME_DIR_GAP_CAP", 8.0))
        alt = _best_same_outcome_alternate(_rank_crs(crs, set()), out[0], gap_cap=same_dir_gap)
        if not alt:
            for score, odd in _rank_crs(crs, exclude):
                if _score_outcome(score) == pri_out:
                    alt = score
                    break
        if alt and alt != out[0]:
            out = [out[0], alt]

    ranked = _rank_crs(crs, set())
    new_upset = _upset_from_different_outcome(
        ranked, set(out) | {upset_val}, primary_outcome=pri_out,
    )
    if new_upset is not None:
        upset_val = new_upset
    return out, upset_val


def repair_stored_score_picks(
    picks: list[str],
    upset: str | None,
    crs: dict[str, float] | None,
    *,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
    draw_rate: float | None = None,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    sp_draw: float | None = None,
    handicap: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> tuple[list[str], str | None]:
    """Sanitize DB-cached score lines using CRS without a full repredict."""
    if not crs:
        return [s for s in (picks or []) if s and s != "?"][:2], upset
    fixed_picks, fixed_upset = reconcile_likely_upset_cluster(picks, upset, crs)
    fixed_picks = align_score_picks_to_wdl(
        fixed_picks,
        crs,
        win_rate=win_rate,
        draw_rate=draw_rate or max(0.0, 100.0 - win_rate - lose_rate),
        lose_rate=lose_rate,
    )
    pick_outs = {_score_outcome(p) for p in fixed_picks if p}
    if fixed_upset and pick_outs and _score_outcome(fixed_upset) in pick_outs:
        fixed_upset = pick_upset_from_crs(
            crs,
            fixed_picks,
            win_rate=win_rate,
            lose_rate=lose_rate,
            draw_rate=draw_rate,
            sp_win=sp_win,
            sp_lose=sp_lose,
            sp_draw=sp_draw,
            handicap=handicap,
            rank_a=rank_a,
            rank_b=rank_b,
        )
    fixed_picks, fixed_upset, _ = validate_score_picks(
        fixed_picks, fixed_upset, crs, apply_ensure_triple=True,
        win_rate=win_rate, draw_rate=draw_rate or max(0.0, 100.0 - win_rate - lose_rate),
        lose_rate=lose_rate,
    )
    return fixed_picks, fixed_upset


def validate_score_picks(
    best_scores: list[str],
    upset: str | None,
    score_odds: dict[str, float] | None,
    *,
    model_scores: list[str] | None = None,
    min_upset_odd: float = 20.0,
    apply_ensure_triple: bool = False,
    win_rate: float = 50.0,
    draw_rate: float = 28.0,
    lose_rate: float = 50.0,
) -> tuple[list[str], str | None, list[str]]:
    """
    Post-pick validation (luoji.md §8). Returns fixed picks and warning messages.

    Enhanced validation checks:
    - CRS赔率池完整性检查
    - 三选方向覆盖检查（必须至少2个不同赛果方向）
    - 冷门赔率合理性检查
    - 推荐比分是否在赔率池中
    """
    cfg = _get_config()
    warnings: list[str] = []
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    upset_val = upset if upset and upset != "?" else None
    crs = score_odds or {}

    # CRS赔率池完整性检查
    crs_scores = [k for k in crs.keys() if ":" in str(k)]
    if len(crs_scores) < 3:
        warnings.append(f"CRS赔率池仅包含 {len(crs_scores)} 个比分，可能不足以支撑预测")

    if apply_ensure_triple:
        picks, upset_val = ensure_triple_direction_coverage(
            picks, upset_val, crs, model_scores,
        )

    picks, upset_val = reconcile_likely_upset_cluster(picks, upset_val, crs)

    # 三选方向覆盖检查（必须至少2个不同赛果方向）
    outcomes = _pick_outcomes(picks, upset_val)
    min_coverage = int(cfg.get("MIN_TRIPLE_DIRECTION_COVERAGE", 2))
    if upset_val not in ("胜其它", "平其它", "负其它") and len(outcomes) < min_coverage:
        warnings.append(f"三选方向覆盖不足（仅 {len(outcomes)} 个赛果方向，建议至少 {min_coverage} 个）")

    # 冷门合理性检查
    if upset_val:
        if upset_val in ("胜其它", "平其它", "负其它"):
            if upset_val not in crs:
                warnings.append(f"冷门选项 {upset_val} 不在 CRS 赔率池")
        elif upset_val not in crs:
            warnings.append(f"冷门比分 {upset_val} 不在 CRS 赔率池")
        else:
            try:
                odd = float(crs[upset_val])
                implied = 100.0 / odd if odd > 1.01 else 0.0
                # 增强冷门赔率检查：同时检查下限和上限
                upset_warn_cap = float(cfg.get("UPSET_ODD_WARN_CAP", 20.0))
                if odd > upset_warn_cap:
                    warnings.append(
                        f"冷门比分 {upset_val} 隐含概率 {implied:.1f}% 低于 5% 参考线（赔率 {odd:.2f}）"
                    )
                elif odd < 1.5:
                    warnings.append(
                        f"冷门比分 {upset_val} 隐含概率 {implied:.1f}% 过高，可能不适合作为冷门"
                    )
            except (TypeError, ValueError):
                pass

    # 推荐比分是否在赔率池中
    for score in picks:
        if score and score not in crs and ":" in score:
            warnings.append(f"推荐比分 {score} 不在 CRS 赔率池")

    # 方向一致性检查：如果primary和secondary同向，检查赔率差距是否合理
    if len(picks) >= 2:
        try:
            outcome1 = _score_outcome(picks[0])
            outcome2 = _score_outcome(picks[1])
            if outcome1 == outcome2 and outcome1 not in ("胜其它", "平其它", "负其它"):
                odd1 = crs.get(picks[0])
                odd2 = crs.get(picks[1])
                if odd1 and odd2:
                    gap = float(odd2) - float(odd1)
                    if gap > 8.0:
                        warnings.append(
                            f"同向比分 {picks[0]} → {picks[1]} 赔率差距过大（{gap:.2f}），建议确认"
                        )
        except (TypeError, ValueError):
            pass

    picks = _fix_opposite_outcome_likely_pair(
        picks, crs, win_rate=win_rate, draw_rate=draw_rate, lose_rate=lose_rate,
    )

    return picks, upset_val, warnings


def _fix_opposite_outcome_likely_pair(
    picks: list[str],
    crs: dict[str, float],
    *,
    win_rate: float = 50.0,
    draw_rate: float = 28.0,
    lose_rate: float = 50.0,
) -> list[str]:
    """Hot pair must not mix home win + away win (e.g. 2:1 with 1:2)."""
    if len(picks) < 2 or not crs:
        return picks
    o0, o1 = _score_outcome(picks[0]), _score_outcome(picks[1])
    if {o0, o1} != {"win", "lose"}:
        return picks
    dom, _ = wdl_outcome_margin(win_rate, draw_rate, lose_rate)
    ranked = _rank_crs(crs, set())
    primary = _best_crs_for_outcome(ranked, crs, dom, set(), None)
    if not primary:
        return picks
    sec = _best_crs_for_outcome(ranked, crs, dom, {primary}, None)
    if not sec:
        sec = _best_crs_for_outcome(ranked, crs, "draw", {primary}, None)
    return [primary, sec] if sec else [primary]


def run_full_score_pipeline(
    crs: dict[str, float],
    *,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    expected_a: float = 1.2,
    expected_b: float = 1.0,
    model_scores: list[str] | None = None,
    stage: str | None = None,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    sp_draw: float | None = None,
    handicap: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
    group_context: dict | None = None,
    odds_dict: dict | None = None,
    rule_result=None,
    team_a: dict | None = None,
    team_b: dict | None = None,
    skip_wdl_resilience: bool = False,
) -> tuple[list[str], str | None, list[str], list[str]]:
    """
    Unified CRS score pick pipeline — production, backtest, batch API must all use this.
    Returns (best_scores[:2], upset, all_picks, warnings).

    Set skip_wdl_resilience=True when the caller has already applied W/D/L context
    adjustments (e.g. via CalibratedRuleEngine / apply_context_to_rates) to avoid
    double-counting resilience signals on win/draw/lose rates.
    """
    hints = [s for s in (model_scores or []) if s and s != "?"]
    pre_upset: str | None = None
    crs, hints, pre_upset = prepare_pipeline_crs_and_hints(
        crs or None,
        expected_a=expected_a,
        expected_b=expected_b,
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
        model_scores=hints or None,
        stage=stage,
        rank_a=rank_a,
        rank_b=rank_b,
        sp_win=sp_win,
        sp_draw=sp_draw,
        sp_lose=sp_lose,
    )
    if not crs:
        fallback = hints[:2] if hints else ["?"]
        return fallback, pre_upset, fallback + ([pre_upset] if pre_upset else []), []

    win_rate, draw_rate, lose_rate = cap_knockout_wdl_to_market(
        win_rate, draw_rate, lose_rate, stage,
        sp_win=sp_win, sp_draw=sp_draw, sp_lose=sp_lose,
    )

    # ── New weighted-ensemble pipeline (feature-flagged) ──
    from service.score_pick_config import get_config
    cfg = get_config()
    if cfg.get("PIPELINE_USE_NEW_ENSEMBLE", True):
        from service.score_pipeline import ScorePredictionPipeline
        _pipeline = ScorePredictionPipeline()
        return _pipeline.run(
            crs,
            win_rate=win_rate, draw_rate=draw_rate, lose_rate=lose_rate,
            expected_a=expected_a, expected_b=expected_b,
            model_scores=hints or None, stage=stage,
            sp_win=sp_win, sp_lose=sp_lose, sp_draw=sp_draw,
            handicap=handicap, rank_a=rank_a, rank_b=rank_b,
            group_context=group_context, odds_dict=odds_dict,
            rule_result=rule_result, team_a=team_a, team_b=team_b,
            skip_wdl_resilience=skip_wdl_resilience,
        )

    # ── Legacy 20-step pipeline (kept for reference) ──
    from service.score_context import adjust_wdl_for_resilience, detect_resilience_signals
    _res_odds = dict(odds_dict or {})
    if sp_win is not None:
        _res_odds.setdefault("win_win", sp_win)
    if sp_lose is not None:
        _res_odds.setdefault("win_lose", sp_lose)
    if sp_draw is not None:
        _res_odds.setdefault("draw", sp_draw)
    if handicap:
        _res_odds.setdefault("handicap", handicap)
    if odds_dict:
        _ctx_odds = dict(odds_dict)
        if handicap:
            _ctx_odds.setdefault("handicap", handicap)
        if sp_win is not None:
            _ctx_odds.setdefault("win_win", sp_win)
        if sp_lose is not None:
            _ctx_odds.setdefault("win_lose", sp_lose)
        if sp_draw is not None:
            _ctx_odds.setdefault("draw", sp_draw)
    elif sp_win and sp_lose:
        _ctx_odds = {"win_win": sp_win, "win_lose": sp_lose}
        if sp_draw is not None:
            _ctx_odds["draw"] = sp_draw
    else:
        _ctx_odds = None
    _resilience = detect_resilience_signals(
        group_context, _res_odds, rank_a, rank_b, team_a=team_a or {}, team_b=team_b or {},
    )
    if not skip_wdl_resilience:
        win_rate, draw_rate, lose_rate = adjust_wdl_for_resilience(
            win_rate, draw_rate, lose_rate, _resilience,
        )

    # Apply stage-based draw uplift — skip MD3 must-win (avoid washing out align margin)
    ctx = group_context or {}
    if not (
        ctx.get("matchday") == 3
        and ctx.get("stage") == "小组赛"
        and (ctx.get("must_win_a") or ctx.get("must_win_b") or ctx.get("both_must_win"))
    ):
        win_rate, draw_rate, lose_rate = apply_stage_draw_adjustment(
            win_rate, draw_rate, lose_rate, stage, sp_win=sp_win, sp_lose=sp_lose,
        )

    best = pick_crs_anchored_scores(
        crs,
        win_rate=win_rate,
        lose_rate=lose_rate,
        draw_rate=draw_rate,
        expected_a=expected_a,
        expected_b=expected_b,
        model_scores=hints or None,
        stage=stage,
        sp_win=sp_win,
        sp_draw=sp_draw,
        sp_lose=sp_lose,
        rank_a=rank_a,
        rank_b=rank_b,
    )
    best = prefer_poisson_primary_when_close(best, hints or None, crs)
    if group_context is not None and rule_result is not None:
        from service.calibration_service import CalibratedRuleEngine
        engine = CalibratedRuleEngine()
        best = engine._apply_host_blowout_scores(
            best, crs, group_context, odds_dict, rule_result, team_a, team_b,
        )
    best = boost_heavy_favorite_scores(
        best, crs, win_rate=win_rate, handicap=handicap, rank_a=rank_a, rank_b=rank_b,
        resilience=_resilience,
    )
    best = apply_favourite_blowout_scores(
        best, crs,
        sp_win=sp_win, handicap=handicap, win_rate=win_rate,
        lose_rate=lose_rate, expected_a=expected_a,
        resilience=_resilience,
    )
    best = promote_strong_home_multi_goal(
        best, crs, sp_win=sp_win, sp_draw=sp_draw, win_rate=win_rate,
    )
    best = preserve_one_nil_cluster(best, crs, sp_draw=sp_draw)
    best = refine_favorite_score_cluster(
        best, crs,
        win_rate=win_rate, lose_rate=lose_rate, sp_win=sp_win, sp_lose=sp_lose,
        resilience=_resilience,
    )
    best = apply_favourite_blowout_scores(
        best, crs,
        sp_win=sp_win, handicap=handicap, win_rate=win_rate,
        lose_rate=lose_rate, expected_a=expected_a,
        high_tiers_only=True,
        resilience=_resilience,
    )
    best = promote_extreme_home_favourite(
        best, crs, sp_win=sp_win, handicap=handicap, win_rate=win_rate,
    )
    best = promote_open_game_high_score(
        best, crs,
        expected_a=expected_a, expected_b=expected_b,
        win_rate=win_rate, lose_rate=lose_rate,
    )
    gap = abs(int(rank_a or 50) - int(rank_b or 50))
    best = promote_knockout_blowout_scores(
        best, crs,
        expected_a=expected_a, expected_b=expected_b,
        stage=stage, win_rate=win_rate, lose_rate=lose_rate,
        rank_gap=gap,
    )
    best = promote_narrow_home_win_over_draw(
        best, crs, win_rate=win_rate, lose_rate=lose_rate,
    )
    from service.score_context import apply_contextual_score_adjustments
    best = apply_contextual_score_adjustments(
        best,
        crs,
        group_context=group_context,
        odds_dict=_ctx_odds,
        win_rate=win_rate,
        lose_rate=lose_rate,
        draw_rate=draw_rate,
        expected_a=expected_a,
        expected_b=expected_b,
        rank_a=rank_a,
        rank_b=rank_b,
        team_a=team_a or {},
        team_b=team_b or {},
    )
    best = prefer_close_crs_secondary(best, crs, stage=stage)
    best = align_score_picks_to_wdl(
        best,
        crs,
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
        model_scores=hints or None,
        resilience=_resilience,
        group_context={
            **(group_context or {}),
            **({"handicap": handicap} if handicap else {}),
            **({"rank_a": rank_a, "rank_b": rank_b, "rank_gap": abs(int(rank_a or 50) - int(rank_b or 50))}
               if rank_a is not None and rank_b is not None else {}),
        },
    )
    best = ensure_rout_score_in_likely_pair(
        best, crs, sp_win=sp_win, sp_lose=sp_lose, win_rate=win_rate, lose_rate=lose_rate,
        rank_gap=gap, resilience=_resilience, draw_rate=draw_rate,
    )
    from service.score_context import apply_resilience_to_likely_pair
    best = apply_resilience_to_likely_pair(
        best, crs, _resilience, win_rate=win_rate, lose_rate=lose_rate,
    )
    upset = pick_upset_from_crs(
        crs, best,
        win_rate=win_rate, lose_rate=lose_rate, draw_rate=draw_rate,
        sp_win=sp_win, sp_lose=sp_lose, sp_draw=sp_draw,
        handicap=handicap, rank_a=rank_a, rank_b=rank_b,
        group_context=group_context, team_a=team_a, team_b=team_b,
        odds_dict=_res_odds,
    )
    best, upset = ensure_triple_direction_coverage(best, upset, crs, hints or None)
    best, upset, warnings = validate_score_picks(
        best, upset, crs, model_scores=hints or None, apply_ensure_triple=False,
        win_rate=win_rate, draw_rate=draw_rate, lose_rate=lose_rate,
    )
    all_picks = best + ([upset] if upset else [])
    return best, upset, all_picks, warnings


def canonical_score_recommendations(
    crs: dict[str, float] | None,
    *,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    model_scores: list[str] | None = None,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    sp_draw: float | None = None,
    handicap: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> tuple[list[str], str | None]:
    """
    Single entry for dashboard, schedule batch API, and sporttery plan score lines.
    Always runs the full CRS pipeline with fused AI W/D/L.
    """
    hints = [s for s in (model_scores or []) if s and s != "?"]
    if not crs:
        return hints[:2], None
    best, upset, _, _ = run_full_score_pipeline(
        crs,
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
        model_scores=hints or None,
        sp_win=sp_win,
        sp_lose=sp_lose,
        sp_draw=sp_draw,
        handicap=handicap,
        rank_a=rank_a,
        rank_b=rank_b,
    )
    return best[:2], upset


def pick_crs_anchored_scores(
    score_odds: dict[str, float],
    *,
    win_rate: float,
    lose_rate: float,
    draw_rate: float | None = None,
    expected_a: float = 1.2,
    expected_b: float = 1.0,
    model_scores: list[str] | None = None,
    exclude: set[str] | None = None,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    sp_draw: float | None = None,
    stage: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> list[str]:
    """
    Pick exactly two likely scorelines.

    Primary: CRS anchor with situational promotion (draw / home clean-sheet).
    Secondary: complementary outcome from CRS or model hints.
    """
    ranked = _rank_crs(score_odds, exclude or set())
    if not ranked:
        clean = [s for s in (model_scores or []) if s and s != "?"]
        return clean[:2]

    primary, primary_odd = ranked[0]
    dr = draw_rate if draw_rate is not None else max(0.0, 100.0 - win_rate - lose_rate)
    promo_dr = min(45.0, dr + _stage_draw_promotion_boost(stage))
    total_xg = expected_a + expected_b
    fav_a = win_rate >= lose_rate
    pri_out = _score_outcome(primary)
    market_fav_a = _market_fav_a(sp_win, sp_lose)
    gap_to_second = (ranked[1][1] - primary_odd) if len(ranked) > 1 else 99.0
    competitive = abs(win_rate - lose_rate) < 32 and dr >= 16
    tight = _is_competitive(win_rate, lose_rate, dr)
    slight_favourite = win_rate < 58.0

    # 弱队主场 + 大热门客场 + CRS 首推平局：客队小胜赔接近时升首推（海地 0:1）
    if pri_out == "draw" and _is_heavy_fav_away(lose_rate, sp_lose):
        for score, _ in ranked[1:6]:
            if score == primary:
                continue
            if _score_outcome(score) == "lose" and _draw_close_to_primary(
                ranked, score, primary, ratio_cap=1.15, gap_cap=1.2,
            ):
                return [score, primary]

    # 非明显热门 + 平局 CRS → 可升 2:1 首推（韩国 2:1）
    if (
        pri_out == "draw"
        and competitive
        and slight_favourite
        and total_xg >= 2.15
        and win_rate > lose_rate + 8
        and gap_to_second >= 0.8
    ):
        margin_pick = _best_margin_win(
            ranked, fav_a, expected_a, expected_b, skip={primary},
        )
        if margin_pick:
            try:
                ga, gb = map(int, margin_pick.split(":"))
                # 仅升 2:1/1:2 类比分，避免误升 1:0（澳大利亚）
                if abs(ga - gb) == 1 and (ga + gb) >= 3:
                    return [margin_pick, primary]
            except ValueError:
                pass

    # 大热门客场 + 弱队主场守平：次推 0:0（库拉索 0:0 厄瓜多尔）
    away_market_fav = sp_lose is not None and sp_win is not None and sp_lose < sp_win
    if (
        pri_out == "lose"
        and away_market_fav
        and int(rank_a or 50) >= 75
        and abs(int(rank_a or 50) - int(rank_b or 50)) >= 35
    ):
        cmap = _crs_map(ranked)
        draw_pick = "0:0" if cmap.get("0:0") else _best_draw(ranked, {primary})
        if draw_pick:
            d_odd = cmap.get(draw_pick)
            if d_odd is not None and d_odd <= 12.0:
                return [primary, draw_pick]

    # 大热门客场：平局 CRS 接近时升首推（卡塔尔 1:1）
    if _is_heavy_fav_away(lose_rate, sp_lose) and pri_out == "lose":
        draw_pick = _best_draw(ranked, set())
        if draw_pick and _draw_close_to_primary(
            ranked, primary, draw_pick, ratio_cap=1.85, gap_cap=3.0,
        ):
            return [draw_pick, primary]
        if draw_pick:
            return [primary, draw_pick]

    # 平局 CRS 与首推胜比分赔接近时升首推（巴西 1:1）— 需市场支持平局
    if pri_out != "draw":
        draw_pick = _best_draw(ranked, {primary})
        if draw_pick and _should_promote_draw_to_primary(
            ranked, primary, draw_pick,
            draw_rate=promo_dr, pri_out=pri_out,
            sp_win=sp_win, sp_draw=sp_draw,
        ):
            return [draw_pick, primary]

    # 势均力敌 + CRS 首推平局 + 欧赔略看好主队：阶段平局加成高时不升主胜
    if pri_out == "draw" and tight and promo_dr < 42 and win_rate >= 48:
        fav_home = market_fav_a if market_fav_a is not None else fav_a
        if fav_home and not _is_heavy_fav_home(win_rate, sp_win):
            home_win = _best_home_win(ranked, {primary}, expected_a=expected_a)
            if (
                home_win
                and expected_a >= 1.0
                and _home_win_close_to_draw(ranked, primary, home_win)
            ):
                return [home_win, primary]

    # 平局 CRS 首推 + 客队 SPF 略热且 1:0 赔接近：升主胜首推（科特迪瓦 1:0）
    if pri_out == "draw" and market_fav_a is False and sp_lose and sp_win:
        if sp_lose < sp_win - 0.2:
            cmap = _crs_map(ranked)
            draw_odd = cmap.get(primary)
            one_nil_odd = cmap.get("1:0")
            if draw_odd and one_nil_odd and (one_nil_odd - draw_odd) <= 3.5:
                return ["1:0", primary]

    # 平局首选 + 市场看好客队：次推优先主队小胜 1:0（科特迪瓦 1:0）
    if pri_out == "draw" and market_fav_a is False:
        for score, odd in ranked[1:8]:
            if score == primary:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga == 1 and gb == 0 and odd <= 9.0:
                return [primary, score]

    # 大热门主场 + CRS 首推平局（加拿大 1:1）：保留平局，次推小胜
    if pri_out == "draw" and _is_heavy_fav_home(win_rate, sp_win):
        for score, _ in ranked[1:]:
            if score == primary:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga > gb:
                return [primary, score]

    # 势均力敌 + CRS 首推平局 + 模型略看好主队（兜底）
    if pri_out == "draw" and abs(win_rate - lose_rate) < 22:
        fav_home = market_fav_a if market_fav_a is not None else fav_a
        if fav_home:
            home_win = _best_home_win(ranked, {primary}, expected_a=expected_a)
            if home_win:
                return [primary, home_win]

    secondary = _pick_secondary(
        ranked, primary, pri_out, fav_a, total_xg, model_scores, exclude or set(),
        market_fav_a=market_fav_a,
        expected_a=expected_a,
    )
    if secondary and secondary != primary:
        return [primary, secondary]
    return [primary]


def _best_rout_upset_score(
    ranked: list[tuple[str, float]],
    exclude: set[str],
    *,
    min_goals: int = 4,
    max_odd: float = 35.0,
    sp_win: float | None = None,
) -> str | None:
    """Rout scoreline within odd cap — shutouts for ultra-deep SPF, else max total goals."""
    prefer_shutout = sp_win is not None and sp_win < 1.42
    best: tuple | None = None
    for score, odd in ranked:
        if score in exclude or score == "胜其它" or odd > max_odd:
            continue
        if ":" not in score:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if ga > gb and ga >= min_goals and gb <= 1:
            if prefer_shutout:
                key = (ga, -gb, -odd)
            else:
                key = (ga + gb, ga, -odd)
            if best is None or key > best[0]:
                best = (key, score)
    return best[1] if best else None


def ensure_rout_score_in_likely_pair(
    best_scores: list[str],
    score_odds: dict[str, float] | None,
    *,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
    rank_gap: int = 0,
    resilience: dict | None = None,
    draw_rate: float | None = None,
) -> list[str]:
    """Deep favourite: keep a high rout CRS line in the two likely picks (4:0 / 0:3)."""
    from service.score_context import should_skip_rout_boost

    if not best_scores or not score_odds:
        return best_scores
    if should_skip_rout_boost(resilience or {}, draw_rate):
        return best_scores

    picks = [s for s in best_scores if s and s != "?"][:2]
    if not picks:
        return best_scores

    # Away deep favourite (Brazil 0:3 @ Scotland)
    if (
        sp_lose is not None
        and sp_lose < 1.45
        and lose_rate >= 52
        and _score_outcome(picks[0]) == "lose"
    ):
        sec = picks[1] if len(picks) > 1 else picks[0]
        # Moderate away fav (sp ~1.25–1.45): 1:3 more common than 0:3 rout
        if sp_lose >= 1.25 and "1:3" in score_odds:
            picks = ["1:3" if p == "0:3" else p for p in picks]
            sec = picks[1] if len(picks) > 1 else picks[0]
        if sp_lose < 1.25 and "0:3" in score_odds and picks[0] != "0:3":
            if sec == "0:3":
                sec = "0:2" if "0:2" in score_odds else picks[0]
            return ["0:3", sec if sec != "0:3" else picks[0]]
        if len(picks) >= 2:
            return picks[:2]
        for rout in ("1:3", "0:2") if sp_lose >= 1.25 else ("0:3", "0:2", "1:3"):
            if rout in score_odds and rout not in picks:
                return [picks[0], rout]
        return picks

    if sp_win is None:
        return picks
    if win_rate < 56.0:
        return picks
    deep_sp = sp_win < 1.42
    moderate_rout = sp_win < 1.60 and win_rate >= 58.0 and rank_gap >= 28
    if not deep_sp and not moderate_rout:
        return picks
    if _score_outcome(picks[0]) != "win":
        return picks
    ranked = _rank_crs(score_odds, set())
    rout = _best_rout_upset_score(
        ranked, {picks[0]}, min_goals=4, max_odd=35.0, sp_win=sp_win,
    )
    if not rout or rout == picks[0]:
        return picks
    return [picks[0], rout]


def _best_high_home_win(
    ranked: list[tuple[str, float]],
    exclude: set[str],
    *,
    min_goals: int = 3,
) -> str | None:
    best: tuple[int, str] | None = None
    for score, _ in ranked:
        if score in exclude or score == "胜其它":
            continue
        if ":" not in score:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if ga > gb and ga >= min_goals and gb <= 1:
            if best is None or ga > best[0]:
                best = (ga, score)
    return best[1] if best else None


def _market_draw_rate(
    draw_rate: float,
    sp_win: float | None,
    sp_draw: float | None,
    sp_lose: float | None,
) -> float:
    if not (sp_win and sp_draw and sp_lose):
        return draw_rate
    try:
        over = 1 / float(sp_win) + 1 / float(sp_draw) + 1 / float(sp_lose)
        implied = (1 / float(sp_draw)) / over * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return draw_rate
    if draw_rate < 22 and implied >= 24:
        return implied
    if abs(draw_rate - implied) > 12:
        return (draw_rate + implied) / 2
    return draw_rate


def pick_upset_from_crs(
    score_odds: dict[str, float],
    best_scores: list[str],
    *,
    win_rate: float,
    lose_rate: float,
    draw_rate: float | None = None,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    sp_draw: float | None = None,
    handicap: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
    group_context: dict | None = None,
    team_a: dict | None = None,
    team_b: dict | None = None,
    odds_dict: dict | None = None,
) -> str | None:
    """Pick upset scoreline from CRS pool — prefer plausible draw or underdog win."""
    cfg = _get_config()
    ranked = _rank_crs(score_odds, set())
    if not ranked:
        return None
    exclude = {s for s in (best_scores or []) if s and s != "?"}
    dr = draw_rate if draw_rate is not None else max(0.0, 100.0 - win_rate - lose_rate)
    dr = _market_draw_rate(dr, sp_win, sp_draw, sp_lose)
    crs_map = _crs_map(ranked)
    rank_gap = abs(int(rank_a or 50) - int(rank_b or 50))
    hcp = _parse_handicap_line(handicap)

    from service.score_context import detect_resilience_signals, pick_resilience_upset
    resilience = detect_resilience_signals(
        group_context, odds_dict, rank_a, rank_b, team_a=team_a or {}, team_b=team_b or {},
    )
    resilient_upset = pick_resilience_upset(
        score_odds, exclude, resilience, draw_rate=dr, sp_draw=sp_draw,
    )
    if resilient_upset:
        return resilient_upset

    # Cluster pair: likely picks already share favourite outcome — upset must differ
    cluster_min_win = float(cfg.get("UPSET_CLUSTER_MIN_WIN_RATE", 52.0))
    concession_cap = float(cfg.get("UPSET_CONCESSION_ODD_CAP", 16.0))
    same_dir_cap = float(cfg.get("UPSET_SAME_DIR_ODD_CAP", 14.0))

    if len(best_scores or []) >= 2:
        o0 = _score_outcome(best_scores[0])
        o1 = _score_outcome(best_scores[1])
        if o0 == o1 == "win" and win_rate >= cluster_min_win:
            alt = _upset_from_different_outcome(ranked, exclude, primary_outcome="win")
            if alt:
                return alt
        if o0 == o1 == "lose" and lose_rate >= cluster_min_win:
            concessions: list[tuple[float, str]] = []
            for score, odd in ranked:
                if score in exclude:
                    continue
                try:
                    ga, gb = map(int, score.split(":"))
                except ValueError:
                    continue
                if ga >= 1 and gb > ga and odd <= concession_cap:
                    concessions.append((odd, score))
            if concessions:
                concessions.sort(key=lambda x: x[0])
                for _, score in concessions:
                    if score not in exclude:
                        return score
            alt = _upset_from_different_outcome(ranked, exclude, primary_outcome="lose")
            if alt:
                return alt
            if _has_crs_special(score_odds, "负其它"):
                return "负其它"
            for score, odd in ranked:
                if score in exclude:
                    continue
                try:
                    ga, gb = map(int, score.split(":"))
                except ValueError:
                    continue
                if ga > gb and odd <= same_dir_cap:
                    return score

    def _crs_odd(key: str) -> float | None:
        try:
            v = (score_odds or {}).get(key)
            return float(v) if v is not None else crs_map.get(key)
        except (TypeError, ValueError):
            return crs_map.get(key)

    # 深盘热门闷平：0:0 / 1:1 作冷门（西班牙 0:0, 葡萄牙 1:1）
    stalemate_gap = float(cfg.get("RANK_GAP_STALEMATE", 30.0))
    deep_hcp = float(cfg.get("DEEP_HANDICAP_THRESHOLD", -1.5))
    stalemate_odd_limit = float(cfg.get("UPSET_DRAW_DEEP_FAV_LIMIT", 55.0))

    if _is_strong_home_fav(win_rate, sp_win) and hcp <= deep_hcp and rank_gap >= stalemate_gap:
        for stale in ("0:0", "1:1"):
            if stale in exclude:
                continue
            odd = _crs_odd(stale)
            if odd is not None and odd <= stalemate_odd_limit:
                return stale

    # 客队 SPF 热门 + 平局热门：冷门优先主队 1:0（科特迪瓦 1:0）
    home_score_odd = float(cfg.get("UPSET_AWAY_HOME_SCORE_ODD", 9.0))
    if sp_win and sp_lose and sp_lose < sp_win - 0.25:
        for score, odd in ranked:
            if score in exclude:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga == 1 and gb == 0 and odd <= home_score_odd:
                return score

    if _is_heavy_fav_away(lose_rate, sp_lose):
        draw_pick = _best_draw(ranked, exclude)
        minnow_rank = float(cfg.get("RANK_HIGH_MINNOW", 75.0))
        minnow_gap = float(cfg.get("RANK_GAP_BLOWOUT", 35.0))
        zero_zero_odd = float(cfg.get("UPSET_MINNOW_HOME_ZERO_ZERO_ODD", 12.0))
        draw_odd_cap = float(cfg.get("UPSET_DRAW_LOSE_RATE_CAP", 9.5))

        minnow_home = (
            int(rank_a or 50) >= minnow_rank
            and rank_gap >= minnow_gap
            and sp_lose is not None
            and sp_win is not None
            and sp_lose < sp_win
        )
        if minnow_home and crs_map.get("0:0") and "0:0" not in exclude:
            z_odd = crs_map["0:0"]
            if z_odd <= zero_zero_odd:
                return "0:0"
        if draw_pick and lose_rate >= 60.0:
            d_odd = crs_map.get(draw_pick)
            draw_cap = zero_zero_odd if minnow_home else draw_odd_cap
            if d_odd is not None and d_odd <= draw_cap:
                return draw_pick
        for score, _ in ranked:
            if score in exclude:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga > gb:
                return score
        for score, _ in ranked:
            if score in exclude:
                continue
            if _score_outcome(score) == "draw":
                return score

    if _is_strong_home_fav(win_rate, sp_win):
        draw_pick = _best_draw(ranked, exclude)
        if draw_pick:
            return draw_pick
        away_win_cap = float(cfg.get("UPSET_AWAY_WIN_ODD_CAP", 14.0))
        for score, odd in ranked:
            if score in exclude:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if gb > ga and odd <= away_win_cap:
                return score
        if _has_crs_special(score_odds, "胜其它"):
            return "胜其它"

    draw_rate_threshold = float(cfg.get("UPSET_DRAW_RATE_THRESHOLD", 22.0))
    if dr >= draw_rate_threshold:
        for score, _ in ranked:
            if score in exclude:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga == gb and ga >= 2:
                return score
        draw_pick = _best_draw(ranked, exclude)
        if draw_pick:
            return draw_pick

    pri_out = _score_outcome(best_scores[0]) if best_scores else None
    for score, _ in ranked:
        if score in exclude:
            continue
        if pri_out and _score_outcome(score) == pri_out:
            continue
        return score
    return None


def _best_margin_win(
    ranked: list[tuple[str, float]],
    fav_a: bool,
    expected_a: float,
    expected_b: float,
    *,
    skip: set[str],
) -> str | None:
    """Prefer one-goal-margin win when both sides can score (e.g. 2:1)."""
    candidates: list[tuple[float, str]] = []
    for score, odd in ranked:
        if score in skip:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        if fav_a and ga == 2 and gb == 1 and expected_a >= 1.25 and expected_b >= 0.9:
            candidates.append((odd - 2.8, score))
        elif fav_a and ga == 1 and gb == 0:
            candidates.append((odd, score))
        elif not fav_a and ga == 1 and gb == 2 and expected_b >= 1.25 and expected_a >= 0.9:
            candidates.append((odd - 2.8, score))
        elif not fav_a and ga == 0 and gb == 1:
            candidates.append((odd, score))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _pick_secondary(
    ranked: list[tuple[str, float]],
    primary: str,
    pri_out: str,
    fav_a: bool,
    total_xg: float,
    model_scores: list[str] | None,
    exclude: set[str],
    *,
    market_fav_a: bool | None = None,
    expected_a: float = 1.0,
) -> str | None:
    crs_map = _crs_map(ranked)

    alt = _crs_secondary_different_outcome(ranked, primary, pri_out)
    if alt:
        return alt

    if model_scores:
        for ms in model_scores:
            if ms and ms != "?" and ms != primary and ms not in exclude and ms in crs_map:
                return ms

    fav_a_eff = market_fav_a if market_fav_a is not None else fav_a
    fav_out = "win" if fav_a_eff else "lose"
    for score, _ in ranked[1:]:
        if score == primary:
            continue
        out = _score_outcome(score)
        if pri_out == "draw" and out == fav_out:
            return score
        if pri_out != "draw" and out == pri_out:
            return score

    for score, _ in ranked[1:]:
        if score != primary:
            return score
    return None


def align_wdl_to_crs_primary(
    best_scores: list[str],
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
) -> tuple[float, float, float]:
    """When CRS-anchored primary is a draw, tilt W/D/L toward draw."""
    if not best_scores or _score_outcome(best_scores[0]) != "draw":
        return win_rate, draw_rate, lose_rate
    new_draw = max(draw_rate, win_rate, lose_rate, 30.0)
    remainder = 100.0 - new_draw
    fav_is_win = win_rate >= lose_rate
    if fav_is_win:
        ratio = win_rate / max(win_rate + lose_rate, 1.0)
        new_win = round(remainder * ratio, 1)
        new_lose = round(remainder - new_win, 1)
    else:
        ratio = lose_rate / max(win_rate + lose_rate, 1.0)
        new_lose = round(remainder * ratio, 1)
        new_win = round(remainder - new_lose, 1)
    return new_win, new_draw, new_lose


def align_wdl_to_score_picks(
    best_scores: list[str],
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    *,
    stage: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> tuple[float, float, float]:
    """Align W/D/L with score picks — only nudge when primary is a draw."""
    return refine_wdl_after_score_pick(
        best_scores, win_rate, draw_rate, lose_rate,
        stage=stage, rank_a=rank_a, rank_b=rank_b,
    )


def reconcile_wdl_with_score_picks(
    best_scores: list[str],
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    *,
    min_wdl_margin: float = 8.0,
) -> tuple[float, float, float]:
    """When fused W/D/L and primary score pick disagree, trust the score pick."""
    picks = [s for s in (best_scores or []) if s and s != "?"]
    if not picks:
        return win_rate, draw_rate, lose_rate

    score_out = _score_outcome(picks[0])
    dom, margin = wdl_outcome_margin(win_rate, draw_rate, lose_rate)
    if score_out == dom:
        return refine_wdl_after_score_pick(picks, win_rate, draw_rate, lose_rate)
    if margin < min_wdl_margin:
        return win_rate, draw_rate, lose_rate

    rates = {"win": win_rate, "draw": draw_rate, "lose": lose_rate}
    boosted = max(rates[score_out], rates[dom], 55.0)
    remainder = max(100.0 - boosted, 0.0)
    new_draw = round(min(draw_rate, remainder * 0.4), 1) if score_out != "draw" else boosted
    if score_out == "draw":
        new_win = round(remainder * (win_rate / max(win_rate + lose_rate, 1.0)), 1)
        new_lose = round(remainder - new_win, 1)
        return _normalize_wdl(new_win, boosted, new_lose)

    other = "lose" if score_out == "win" else "win"
    new_primary = round(boosted, 1)
    new_other = round(min(rates[other], remainder - new_draw), 1)
    new_draw = round(remainder - new_other, 1)
    if score_out == "win":
        return _normalize_wdl(new_primary, new_draw, new_other)
    return _normalize_wdl(new_other, new_draw, new_primary)


def _normalize_wdl(
    win_rate: float, draw_rate: float, lose_rate: float,
) -> tuple[float, float, float]:
    total = max(win_rate + draw_rate + lose_rate, 1.0)
    scale = 100.0 / total
    w = round(win_rate * scale, 1)
    d = round(draw_rate * scale, 1)
    l = round(100.0 - w - d, 1)
    return max(0.5, w), max(0.5, d), max(0.5, l)


def apply_stage_draw_adjustment(
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    stage: str | None,
    *,
    sp_win: float | None = None,
    sp_lose: float | None = None,
) -> tuple[float, float, float]:
    """Stage-based draw uplift — tuned for 2026 World Cup observed draw rate.

    Boost is scaled down when the market strongly favours one side (sp < 1.60),
    since clear favourites draw less often. Knockout clear favourites skip uplift.
    """
    if not stage:
        return win_rate, draw_rate, lose_rate

    cfg = _get_config()
    boost = stage_draw_boost(stage)

    if boost <= 0:
        return win_rate, draw_rate, lose_rate

    clear_fav = (sp_win is not None and sp_win < 1.60) or (sp_lose is not None and sp_lose < 1.60)
    if clear_fav and is_knockout_stage(stage):
        return win_rate, draw_rate, lose_rate

    # Scale down boost for clear favourites (they draw less often)
    if clear_fav:
        boost *= 0.40   # reduce boost for one-sided matchups

    new_draw = min(42.0, draw_rate + boost)
    shift = new_draw - draw_rate
    return _normalize_wdl(win_rate - shift / 2, new_draw, lose_rate - shift / 2)


def refine_wdl_after_score_pick(
    best_scores: list[str],
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    *,
    stage: str | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> tuple[float, float, float]:
    """Do not rewrite win/lose rates from score — only tilt draw when primary is draw."""
    if not best_scores:
        return win_rate, draw_rate, lose_rate
    if _score_outcome(best_scores[0]) == "draw":
        rank_gap = abs(int(rank_a or 50) - int(rank_b or 50))
        fav_clear = win_rate >= lose_rate + 8.0 or lose_rate >= win_rate + 8.0
        if is_knockout_stage(stage) and fav_clear and rank_gap >= 8:
            return win_rate, draw_rate, lose_rate
        return align_wdl_to_crs_primary(best_scores, win_rate, draw_rate, lose_rate)
    return win_rate, draw_rate, lose_rate


def _pick_outcomes(scores: list[str], upset: str | None) -> set[str]:
    outcomes: set[str] = set()
    for s in scores:
        if s and s != "?":
            outcomes.add(_score_outcome(s))
    if upset and upset not in ("?", "胜其它", "平其它", "负其它"):
        outcomes.add(_score_outcome(upset))
    elif upset == "平其它":
        outcomes.add("draw")
    return outcomes


def ensure_extreme_mismatch_triple_coverage(
    best_scores: list[str],
    upset: str | None,
    crs: dict[str, float],
    *,
    sp_win: float | None = None,
    sp_lose: float | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
    expected_a: float = 1.2,
    expected_b: float = 1.0,
) -> tuple[list[str], str | None]:
    """Cover stalemate and rout tails that triple picks often miss on extreme mismatches."""
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    upset_val = upset if upset and upset != "?" else None
    if not crs or not picks:
        return picks, upset_val

    gap = abs(int(rank_a or 50) - int(rank_b or 50))
    covered = set(picks) | ({upset_val} if upset_val else set())

    # Deep home favourite: keep 0:0/1:1 cold path (Netherlands 0:0 Haiti)
    if sp_win is not None and sp_win <= 1.18 and gap >= 38:
        if _score_outcome(picks[0]) == "win":
            if upset_val == "1:1" and "0:0" in crs:
                upset_val = "0:0"
                covered.add("0:0")
            elif not any(_score_outcome(s) == "draw" for s in covered):
                for draw_score in ("0:0", "1:1"):
                    if draw_score in crs:
                        upset_val = draw_score
                        covered.add(draw_score)
                        break

    # Extreme rout: 胜其它 catches 5:0+ (Germany 7:1 Curacao)
    if sp_win is not None and sp_win <= 1.10 and gap >= 48 and expected_a >= 2.0:
        if _score_outcome(picks[0]) == "win" and _has_crs_special(crs, "胜其它"):
            sec = picks[1] if len(picks) > 1 else picks[0]
            if sec == picks[0] or _score_outcome(sec) == "win":
                picks = [picks[0], "胜其它"]

    # Open high-xG games: ensure a 4+ total-goals line in the triple
    total_xg = expected_a + expected_b
    if total_xg >= 3.0:
        has_high = any(
            sum(map(int, s.split(":"))) >= 4
            for s in covered
            if ":" in s
        )
        if not has_high:
            for score, odd in _rank_crs(crs, covered):
                if sum(map(int, score.split(":"))) >= 4 and float(odd) <= 20.0:
                    if len(picks) >= 2 and _score_outcome(picks[1]) == _score_outcome(picks[0]):
                        picks[1] = score
                    else:
                        upset_val = score
                    break

    return picks[:2], upset_val


def ensure_triple_direction_coverage(
    best_scores: list[str],
    upset: str | None,
    score_odds: dict[str, float],
    model_scores: list[str] | None = None,
) -> tuple[list[str], str | None]:
    """Ensure likely+upset span >=2 W/D/L outcomes when CRS pool allows."""
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    upset_val = upset if upset and upset != "?" else None
    if upset_val in ("胜其它", "平其它", "负其它"):
        return picks, upset_val
    if len(_pick_outcomes(picks, upset_val)) >= 2:
        return picks, upset_val

    primary = picks[0] if picks else None
    pri_out = _score_outcome(primary) if primary else None
    ranked = _rank_crs(score_odds, set())

    if (
        pri_out
        and len(picks) >= 2
        and _score_outcome(picks[1]) == pri_out
        and upset_val
        and _score_outcome(upset_val) == pri_out
    ):
        # Cluster pair + same-direction upset — fix upset only, never mutate picks[1]
        upset_val = _upset_from_different_outcome(ranked, set(picks), primary_outcome=pri_out)

    if len(_pick_outcomes(picks, upset_val)) >= 2:
        return picks, upset_val

    if upset_val:
        return picks, upset_val

    exclude = set(picks)
    for score, _ in ranked:
        if score in exclude or not pri_out or _score_outcome(score) == pri_out:
            continue
        return picks, score
    for ms in model_scores or []:
        if ms and ms not in exclude and pri_out and _score_outcome(ms) != pri_out:
            return picks, ms
    return picks, upset_val
