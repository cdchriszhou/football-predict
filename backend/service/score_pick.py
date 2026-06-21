"""CRS-anchored score selection — market-first with model/xG tie-breakers."""
from __future__ import annotations


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
    ratio_cap: float = 1.55,
    gap_cap: float = 2.0,
) -> bool:
    cmap = _crs_map(ranked)
    pri_odd = cmap.get(primary)
    draw_odd = cmap.get(draw_pick)
    if not pri_odd or not draw_odd:
        return False
    return (draw_odd / pri_odd) <= ratio_cap and (draw_odd - pri_odd) <= gap_cap


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
    return lose_rate >= 55.0 or (sp_lose is not None and sp_lose < 1.55)


def _is_heavy_fav_home(win_rate: float, sp_win: float | None) -> bool:
    return win_rate >= 58.0 or (sp_win is not None and sp_win < 1.62)


def _is_strong_home_fav(win_rate: float, sp_win: float | None) -> bool:
    """Stricter bar for blowout / 胜其它 upset paths — avoids moderate favs like Iran 1.59."""
    if win_rate >= 65.0:
        return True
    return sp_win is not None and sp_win < 1.50


def _is_competitive(win_rate: float, lose_rate: float, draw_rate: float) -> bool:
    return abs(win_rate - lose_rate) < 28 and draw_rate >= 18


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
    if pri_out == "draw" or not draw_pick:
        return False
    if sp_win is not None and sp_win < 1.75:
        return False
    if sp_draw is not None and sp_draw > 3.4:
        return False
    if draw_rate < 30.0:
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
    if sp_win is None:
        cap = 5.0
    elif sp_win < 1.25:
        cap = 8.0
    elif sp_win < 1.45:
        cap = 6.5
    elif sp_win < 1.65:
        cap = 5.0
    else:
        cap = 4.0
    if expected_a >= 2.0 and _parse_handicap_line(handicap) <= -1:
        cap = max(cap, 14.0)
    return cap


def _blowout_tiers(*, high_tiers_only: bool) -> list[tuple[str, float, float | None]]:
    """Shutout-first tiers for deep-favourite rout promotion."""
    tiers: list[tuple[str, float, float | None]] = [
        ("4:0", 1.75, 1.35),
        ("3:0", 1.50, 1.55),
        ("5:0", 2.00, 1.25),
        ("4:1", 1.85, 1.55),
        ("3:1", 1.65, 1.50),
    ]
    if high_tiers_only:
        return [t for t in tiers if t[0] in ("4:0", "3:0", "5:0", "4:1")]
    return tiers


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
) -> list[str]:
    """Deep favourite with -handicap: promote 3:0/4:0 when CRS anchor is a modest home win."""
    if not best_scores or not score_odds or sp_win is None:
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
) -> list[str]:
    """For extreme favourites (deep handicap / huge rank gap), add high-score CRS lines."""
    if not best_scores or not score_odds:
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
    if not stage:
        return 0.0
    if stage == "小组赛":
        return 4.0
    if stage in ("1/8决赛", "1/4决赛", "半决赛"):
        return 6.0
    if stage in ("季军赛", "决赛"):
        return 3.0
    return 0.0


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
    min_margin: float = 6.0,
) -> list[str]:
    """Ensure likely scorelines match the fused W/D/L favourite (AI + market)."""
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    if not picks or not crs:
        return picks
    dom, margin = wdl_outcome_margin(win_rate, draw_rate, lose_rate)
    if margin < min_margin:
        return picks
    ranked = _rank_crs(crs, set())

    if _score_outcome(picks[0]) != dom:
        primary = _best_crs_for_outcome(ranked, crs, dom, set(), model_scores)
        if primary:
            picks[0] = primary

    if len(picks) < 2:
        sec = _best_crs_for_outcome(ranked, crs, dom, {picks[0]}, model_scores)
        if sec:
            picks.append(sec)
    elif margin >= 8 and _score_outcome(picks[1]) != dom:
        sec = _best_crs_for_outcome(ranked, crs, dom, {picks[0]}, model_scores)
        if not sec and dom == "draw":
            alt_out = "lose" if lose_rate >= win_rate else "win"
            sec = _best_side_outcome_moderate(ranked, alt_out, {picks[0]})
        if not sec and dom == "win" and draw_rate >= 20:
            sec = _best_crs_for_outcome(ranked, crs, "draw", {picks[0]}, model_scores)
        elif not sec and dom == "lose" and draw_rate >= 20:
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
    if upset_out not in {_score_outcome(p) for p in out}:
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
        alt = _best_same_outcome_alternate(_rank_crs(crs, set()), out[0], gap_cap=8.0)
        if not alt:
            for score, odd in _rank_crs(crs, exclude):
                if _score_outcome(score) == pri_out:
                    alt = score
                    break
        if alt and alt != out[0]:
            out = [out[0], alt]

    ranked = _rank_crs(crs, set())
    upset_val = _upset_from_different_outcome(
        ranked, set(out) | {upset_val}, primary_outcome=pri_out,
    )
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
) -> tuple[list[str], str | None, list[str]]:
    """
    Post-pick validation (luoji.md §8). Returns fixed picks and warning messages.
    """
    warnings: list[str] = []
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    upset_val = upset if upset and upset != "?" else None
    crs = score_odds or {}

    if apply_ensure_triple:
        picks, upset_val = ensure_triple_direction_coverage(
            picks, upset_val, crs, model_scores,
        )

    picks, upset_val = reconcile_likely_upset_cluster(picks, upset_val, crs)

    outcomes = _pick_outcomes(picks, upset_val)
    if upset_val not in ("胜其它", "平其它", "负其它") and len(outcomes) < 2:
        warnings.append("三选方向覆盖不足（少于2个赛果方向）")

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
                if odd > min_upset_odd:
                    warnings.append(
                        f"冷门比分 {upset_val} 隐含概率 {implied:.1f}% 低于 5% 参考线"
                    )
            except (TypeError, ValueError):
                pass

    for score in picks:
        if score and score not in crs and ":" in score:
            warnings.append(f"推荐比分 {score} 不在 CRS 赔率池")

    return picks, upset_val, warnings


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
) -> tuple[list[str], str | None, list[str], list[str]]:
    """
    Unified CRS score pick pipeline — production, backtest, batch API must all use this.
    Returns (best_scores[:2], upset, all_picks, warnings).
    """
    hints = [s for s in (model_scores or []) if s and s != "?"]
    if not crs:
        fallback = hints[:2] if hints else ["?"]
        return fallback, None, fallback, []

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
    )
    best = apply_favourite_blowout_scores(
        best, crs,
        sp_win=sp_win, handicap=handicap, win_rate=win_rate,
        lose_rate=lose_rate, expected_a=expected_a,
    )
    best = promote_strong_home_multi_goal(
        best, crs, sp_win=sp_win, sp_draw=sp_draw, win_rate=win_rate,
    )
    best = preserve_one_nil_cluster(best, crs, sp_draw=sp_draw)
    best = refine_favorite_score_cluster(
        best, crs,
        win_rate=win_rate, lose_rate=lose_rate, sp_win=sp_win, sp_lose=sp_lose,
    )
    best = apply_favourite_blowout_scores(
        best, crs,
        sp_win=sp_win, handicap=handicap, win_rate=win_rate,
        lose_rate=lose_rate, expected_a=expected_a,
        high_tiers_only=True,
    )
    best = promote_extreme_home_favourite(
        best, crs, sp_win=sp_win, handicap=handicap, win_rate=win_rate,
    )
    best = promote_open_game_high_score(
        best, crs,
        expected_a=expected_a, expected_b=expected_b,
        win_rate=win_rate, lose_rate=lose_rate,
    )
    best = promote_narrow_home_win_over_draw(
        best, crs, win_rate=win_rate, lose_rate=lose_rate,
    )
    from service.score_context import apply_contextual_score_adjustments
    best = apply_contextual_score_adjustments(
        best,
        crs,
        group_context=group_context,
        odds_dict=odds_dict,
        win_rate=win_rate,
        lose_rate=lose_rate,
        draw_rate=draw_rate,
        expected_a=expected_a,
        expected_b=expected_b,
        rank_a=rank_a,
        rank_b=rank_b,
        team_a=(team_a or {}).get("name", ""),
        team_b=(team_b or {}).get("name", ""),
    )
    best = align_score_picks_to_wdl(
        best,
        crs,
        win_rate=win_rate,
        draw_rate=draw_rate,
        lose_rate=lose_rate,
        model_scores=hints or None,
    )
    gap = abs(int(rank_a or 50) - int(rank_b or 50))
    best = ensure_rout_score_in_likely_pair(
        best, crs, sp_win=sp_win, win_rate=win_rate, rank_gap=gap,
    )
    upset = pick_upset_from_crs(
        crs, best,
        win_rate=win_rate, lose_rate=lose_rate, draw_rate=draw_rate,
        sp_win=sp_win, sp_lose=sp_lose, sp_draw=sp_draw,
        handicap=handicap, rank_a=rank_a, rank_b=rank_b,
    )
    best, upset = ensure_triple_direction_coverage(best, upset, crs, hints or None)
    best, upset, warnings = validate_score_picks(
        best, upset, crs, model_scores=hints or None, apply_ensure_triple=False,
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
    win_rate: float = 50.0,
    rank_gap: int = 0,
) -> list[str]:
    """Deep favourite: keep a high rout CRS line in the two likely picks (4:0 / 5:1)."""
    if not best_scores or not score_odds or sp_win is None:
        return best_scores
    if win_rate < 56.0:
        return best_scores
    deep_sp = sp_win < 1.42
    moderate_rout = sp_win < 1.60 and win_rate >= 58.0 and rank_gap >= 28
    if not deep_sp and not moderate_rout:
        return best_scores
    if _score_outcome(best_scores[0]) != "win":
        return best_scores
    ranked = _rank_crs(score_odds, set())
    rout = _best_rout_upset_score(
        ranked, {best_scores[0]}, min_goals=4, max_odd=35.0, sp_win=sp_win,
    )
    if not rout or rout == best_scores[0]:
        return best_scores
    return [best_scores[0], rout]


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
) -> str | None:
    """Pick upset scoreline from CRS pool — prefer plausible draw or underdog win."""
    ranked = _rank_crs(score_odds, set())
    if not ranked:
        return None
    exclude = {s for s in (best_scores or []) if s and s != "?"}
    dr = draw_rate if draw_rate is not None else max(0.0, 100.0 - win_rate - lose_rate)
    dr = _market_draw_rate(dr, sp_win, sp_draw, sp_lose)
    crs_map = _crs_map(ranked)
    rank_gap = abs(int(rank_a or 50) - int(rank_b or 50))
    hcp = _parse_handicap_line(handicap)

    # Cluster pair: likely picks already share favourite outcome — upset must differ
    if len(best_scores or []) >= 2:
        o0 = _score_outcome(best_scores[0])
        o1 = _score_outcome(best_scores[1])
        if o0 == o1 == "win" and win_rate >= 52:
            alt = _upset_from_different_outcome(ranked, exclude, primary_outcome="win")
            if alt:
                return alt
        if o0 == o1 == "lose" and lose_rate >= 52:
            concessions: list[tuple[float, str]] = []
            for score, odd in ranked:
                if score in exclude:
                    continue
                try:
                    ga, gb = map(int, score.split(":"))
                except ValueError:
                    continue
                if ga >= 1 and gb > ga and odd <= 16.0:
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
                if ga > gb and odd <= 14.0:
                    return score

    def _crs_odd(key: str) -> float | None:
        try:
            v = (score_odds or {}).get(key)
            return float(v) if v is not None else crs_map.get(key)
        except (TypeError, ValueError):
            return crs_map.get(key)

    # 深盘热门闷平：0:0 / 1:1 作冷门（西班牙 0:0）
    if _is_strong_home_fav(win_rate, sp_win) and hcp <= -2 and rank_gap >= 40:
        for stale in ("0:0", "1:1"):
            if stale in exclude:
                continue
            odd = _crs_odd(stale)
            if odd is not None and odd <= 40.0:
                return stale

    # 客队 SPF 热门 + 平局热门：冷门优先主队 1:0（科特迪瓦 1:0）
    if sp_win and sp_lose and sp_lose < sp_win - 0.25:
        for score, odd in ranked:
            if score in exclude:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if ga == 1 and gb == 0 and odd <= 9.0:
                return score

    if _is_heavy_fav_away(lose_rate, sp_lose):
        draw_pick = _best_draw(ranked, exclude)
        minnow_home = (
            int(rank_a or 50) >= 75
            and rank_gap >= 35
            and sp_lose is not None
            and sp_win is not None
            and sp_lose < sp_win
        )
        if minnow_home and crs_map.get("0:0") and "0:0" not in exclude:
            z_odd = crs_map["0:0"]
            if z_odd <= 12.0:
                return "0:0"
        if draw_pick and lose_rate >= 60.0:
            d_odd = crs_map.get(draw_pick)
            minnow_home = int(rank_a or 50) >= 75 and rank_gap >= 35
            if d_odd is not None and d_odd <= (11.0 if minnow_home else 9.5):
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
        for score, odd in ranked:
            if score in exclude:
                continue
            try:
                ga, gb = map(int, score.split(":"))
            except ValueError:
                continue
            if gb > ga and odd <= 14.0:
                return score
        if _has_crs_special(score_odds, "胜其它"):
            return "胜其它"

    if dr >= 22:
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
) -> tuple[float, float, float]:
    """Align W/D/L with score picks — only nudge when primary is a draw."""
    return refine_wdl_after_score_pick(best_scores, win_rate, draw_rate, lose_rate)


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
) -> tuple[float, float, float]:
    """Stage-based draw uplift (luoji.md §2.2, scaled for stability)."""
    if not stage:
        return win_rate, draw_rate, lose_rate
    boost = 0.0
    if stage == "小组赛":
        boost = 7.5
    elif stage in ("1/8决赛", "1/4决赛", "半决赛"):
        boost = 12.0
    elif stage in ("季军赛", "决赛"):
        boost = 6.0
    if boost <= 0:
        return win_rate, draw_rate, lose_rate
    new_draw = min(42.0, draw_rate + boost)
    shift = new_draw - draw_rate
    return _normalize_wdl(win_rate - shift / 2, new_draw, lose_rate - shift / 2)


def refine_wdl_after_score_pick(
    best_scores: list[str],
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
) -> tuple[float, float, float]:
    """Do not rewrite win/lose rates from score — only tilt draw when primary is draw."""
    if not best_scores:
        return win_rate, draw_rate, lose_rate
    if _score_outcome(best_scores[0]) == "draw":
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
