"""
Context-aware score pick adjustments.

Combines European + Asian handicap markets, live group standings,
table position, and projected knockout path pressure.
"""
from __future__ import annotations

from service.score_pick import (
    _best_draw,
    _best_home_win,
    _crs_map,
    _rank_crs,
    _score_outcome,
)

# FIFA 48-team R16: group winner vs paired group runner-up (BracketService)
_R16_WINNER_VS_RUNNER: dict[str, str] = {
    "A": "B",
    "C": "D",
    "E": "F",
    "G": "H",
    "I": "J",
    "K": "L",
}

# Runner-up from group X often meets winner of paired group
_R16_RUNNER_VS_WINNER: dict[str, str] = {
    "B": "A",
    "D": "C",
    "F": "E",
    "H": "G",
    "J": "I",
    "L": "K",
}


def _parse_handicap(handicap: str | None) -> float:
    if not handicap:
        return 0.0
    try:
        return float(str(handicap).replace("+", ""))
    except ValueError:
        return 0.0


def _group_position(ctx: dict, side: str) -> int:
    """1-based group rank from pre-match table; 0 if unknown."""
    table = ctx.get("group_table") or []
    st = ctx.get(f"standing_{side}") or {}
    team = st.get("team")
    if not team:
        return 0
    for i, row in enumerate(table, 1):
        if row.get("team") == team:
            return i
    return 0


def _project_finish_band(ctx: dict, side: str) -> str:
    """
    Rough knockout outlook from points + matchday.
    leading | chasing | danger | out
    """
    st = ctx.get(f"standing_{side}") or {}
    if not st.get("played"):
        return "unknown"
    pos = _group_position(ctx, side)
    pts = int(st.get("points") or 0)
    md = int(ctx.get("matchday") or 0)
    if pos == 1 and pts >= 4 and md >= 2:
        return "leading"
    if pos <= 2 and pts >= 3:
        return "chasing"
    if ctx.get(f"must_win_{side}") or pts <= 1:
        return "danger"
    if pos >= 3 and pts <= 2:
        return "danger"
    return "chasing"


def enrich_knockout_outlook(
    ctx: dict,
    team_a: str,
    team_b: str,
    rank_a: int,
    rank_b: int,
    *,
    paired_group_ranks: dict[str, list[int]] | None = None,
) -> dict:
    """
    Attach projected R16 opponent strength and path pressure to group_context.

    paired_group_ranks: {group_letter: [fifa_rank, ...]} for cross-group lookup.
    """
    group = (ctx.get("group_name") or "").strip().upper()
    if not group or ctx.get("stage") != "小组赛":
        return ctx

    md = int(ctx.get("matchday") or 0)
    if md < 2:
        return ctx

    def _opponent_rank_if(side: str, band: str) -> int | None:
        if band == "leading" and group in _R16_WINNER_VS_RUNNER:
            pg = _R16_WINNER_VS_RUNNER[group]
        elif band in ("chasing", "danger") and group in _R16_RUNNER_VS_WINNER:
            pg = _R16_RUNNER_VS_WINNER[group]
        else:
            return None
        ranks = (paired_group_ranks or {}).get(pg) or []
        if not ranks:
            return None
        # Winner slot → face 2nd-tier opponent; chasing → likely group winner (top rank)
        if band == "leading":
            return sorted(ranks)[1] if len(ranks) > 1 else ranks[0]
        return min(ranks)

    for side, team, rk in (("a", team_a, rank_a), ("b", team_b, rank_b)):
        band = _project_finish_band(ctx, side)
        ctx[f"finish_band_{side}"] = band
        ctx[f"group_rank_{side}"] = _group_position(ctx, side)
        opp_rank = _opponent_rank_if(side, band)
        ctx[f"r16_opponent_rank_{side}"] = opp_rank
        pressure = 0.0
        if ctx.get(f"must_win_{side}"):
            pressure += 0.35
        if ctx.get(f"need_goals_{side}"):
            pressure += 0.25
        if ctx.get(f"qualified_{side}"):
            pressure -= 0.30
        if band == "leading" and opp_rank and opp_rank < rk - 5:
            # Leading but R16 draw looks tough → slight conservatism in last group game
            pressure -= 0.12
        if band == "danger" and md == 3:
            pressure += 0.20
        ctx[f"path_pressure_{side}"] = round(max(-0.4, min(0.6, pressure)), 2)

    ctx["knockout_outlook_note"] = _format_knockout_note(ctx, team_a, team_b)
    return ctx


def _format_knockout_note(ctx: dict, team_a: str, team_b: str) -> str:
    parts = []
    for side, name in (("a", team_a), ("b", team_b)):
        band = ctx.get(f"finish_band_{side}", "")
        gr = ctx.get(f"group_rank_{side}") or 0
        opp = ctx.get(f"r16_opponent_rank_{side}")
        if not band or band == "unknown":
            continue
        label = {"leading": "领跑", "chasing": "争二", "danger": "抢分", "out": "出局边缘"}.get(band, band)
        seg = f"{name}小组第{gr}位({label})" if gr else f"{name}({label})"
        if opp:
            seg += f"，出线后或遇FIFA#{opp}档对手"
        parts.append(seg)
    return "；".join(parts)


def market_score_profile(odds_dict: dict | None) -> dict:
    """Derive score tendencies from fused European + Asian handicap markets."""
    o = odds_dict or {}
    sp_win = float(o.get("win_win") or 0)
    sp_lose = float(o.get("win_lose") or 0)
    sp_draw = float(o.get("draw") or 0)
    hcp = _parse_handicap(o.get("handicap"))
    hcp_win = float(o.get("handicap_win") or 0)
    hcp_lose = float(o.get("handicap_lose") or 0)
    ou = float(o.get("over_under") or 2.5)
    imp_win = float(o.get("imp_win") or 0)
    imp_draw = float(o.get("imp_draw") or 0)
    imp_lose = float(o.get("imp_lose") or 0)

    fav_a = sp_win > 0 and sp_lose > 0 and sp_win < sp_lose
    fav_clear = (imp_win >= 55 or imp_lose >= 55) if (imp_win and imp_lose) else (
        sp_win < 1.65 or sp_lose < 1.65
    )
    deep_fav = sp_win < 1.45 or sp_lose < 1.45
    drawish = imp_draw >= 30 or (sp_draw and sp_draw < 3.05)
    low_total = ou <= 2.25
    high_total = ou >= 2.75

    cover_a = hcp <= -0.5 and hcp_win > 0 and hcp_win < 2.05
    cover_b = hcp >= 0.5 and hcp_lose > 0 and hcp_lose < 2.05

    return {
        "fav_a": fav_a,
        "fav_clear": fav_clear,
        "deep_fav": deep_fav,
        "drawish": drawish,
        "low_total": low_total,
        "high_total": high_total,
        "handicap": hcp,
        "cover_a": cover_a,
        "cover_b": cover_b,
        "ou_line": ou,
        "imp_win": imp_win,
        "imp_draw": imp_draw,
        "imp_lose": imp_lose,
    }


def _pick_from_crs(
    crs: dict,
    *,
    outcome: str | None = None,
    min_goals: int = 0,
    max_goals: int = 99,
    exclude: set[str] | None = None,
    prefer: list[str] | None = None,
) -> str | None:
    ranked = _rank_crs(crs, exclude or set())
    if prefer:
        cmap = _crs_map(ranked)
        for score in prefer:
            if score in cmap and (not outcome or _score_outcome(score) == outcome):
                return score
    for score, odd in ranked:
        if odd > 18.0:
            continue
        if outcome and _score_outcome(score) != outcome:
            continue
        try:
            ga, gb = map(int, score.split(":"))
        except ValueError:
            continue
        total = ga + gb
        if total < min_goals or total > max_goals:
            continue
        return score
    return None


def apply_contextual_score_adjustments(
    best_scores: list[str],
    crs: dict[str, float],
    *,
    group_context: dict | None = None,
    odds_dict: dict | None = None,
    win_rate: float = 50.0,
    lose_rate: float = 50.0,
    draw_rate: float | None = None,
    expected_a: float = 1.2,
    expected_b: float = 1.0,
    rank_a: int | None = None,
    rank_b: int | None = None,
    team_a: str = "",
    team_b: str = "",
) -> list[str]:
    """
    Final context pass: standings motivation, euro/asian handicap, knockout path.
    """
    picks = [s for s in (best_scores or []) if s and s != "?"][:2]
    if not picks or not crs:
        return picks

    ctx = group_context or {}
    dr = draw_rate if draw_rate is not None else max(0.0, 100.0 - win_rate - lose_rate)
    market = market_score_profile(odds_dict)
    ranked = _rank_crs(crs, set())
    fav_a = win_rate >= lose_rate

    def _replace_primary(score: str) -> None:
        if score and score in crs:
            picks[0] = score

    def _replace_secondary(score: str) -> None:
        if not score or score not in crs:
            return
        if len(picks) < 2:
            picks.append(score)
        else:
            picks[1] = score

    # ── 1. Euro + Asian handicap alignment ──
    hcp = market["handicap"]
    if market["deep_fav"] and market["fav_a"] and market["cover_a"]:
        rout = _pick_from_crs(
            crs, outcome="win", min_goals=3, exclude=set(picks),
            prefer=["2:0", "3:0", "3:1", "2:1"],
        )
        if rout and hcp <= -1.0:
            _replace_primary(rout)
    elif market["deep_fav"] and not market["fav_a"] and market["cover_b"]:
        rout = _pick_from_crs(
            crs, outcome="lose", min_goals=3, exclude=set(picks),
            prefer=["0:2", "0:3", "1:3", "1:2"],
        )
        if rout and hcp >= 1.0:
            _replace_primary(rout)
    elif market["drawish"] and dr >= 28 and market["low_total"]:
        draw_pick = _pick_from_crs(crs, outcome="draw", prefer=["1:1", "0:0"])
        if draw_pick and _score_outcome(picks[0]) != "draw":
            _replace_primary(draw_pick)
    elif market["high_total"] and (expected_a + expected_b) >= 2.6:
        open_pick = _pick_from_crs(
            crs, min_goals=3, exclude=set(picks),
            prefer=["2:1", "1:2", "2:2", "3:1", "1:3"],
        )
        if open_pick:
            _replace_secondary(open_pick)

    # Narrow fav: Asian -0.5 / euro ~1.85 → 1:0 / 0:1
    if not market["deep_fav"] and market["fav_clear"]:
        if market["fav_a"] and hcp <= -0.5:
            narrow = _best_home_win(ranked, set(picks), expected_a=expected_a) or "1:0"
            if narrow in crs:
                _replace_primary(narrow)
        elif not market["fav_a"] and hcp >= 0.5:
            narrow = _pick_from_crs(crs, outcome="lose", prefer=["0:1", "1:2"])
            if narrow:
                _replace_primary(narrow)

    # ── 2. Group standings: points, GD, table rank ──
    md = int(ctx.get("matchday") or 0)
    if md >= 2 and ctx.get("stage") == "小组赛":
        # 默契平局 / 双方可接受平局
        if ctx.get("both_need_draw") and dr >= 22:
            coll = _pick_from_crs(crs, outcome="draw", prefer=["1:1", "0:0"])
            if coll:
                _replace_primary(coll)
                sec = "0:0" if coll == "1:1" and crs.get("0:0") else "1:1"
                if sec in crs and sec != coll:
                    _replace_secondary(sec)

        for side, is_a in (("a", True), ("b", False)):
            qualified = ctx.get(f"qualified_{side}")
            must_win = ctx.get(f"must_win_{side}")
            need_goals = ctx.get(f"need_goals_{side}")
            pos = int(ctx.get(f"group_rank_{side}") or 0)
            st = ctx.get(f"standing_{side}") or {}
            gpg = (st.get("goals_for", 0) / st["played"]) if st.get("played") else 0

            if qualified and md == 3 and not must_win:
                low = _pick_from_crs(
                    crs, max_goals=2, exclude=set(picks),
                    prefer=["1:0", "0:1", "0:0", "1:1"],
                )
                if low:
                    _replace_secondary(low)

            if must_win and need_goals:
                if is_a and fav_a:
                    aggressive = _pick_from_crs(
                        crs, outcome="win", min_goals=3, prefer=["2:1", "3:1", "3:0"],
                    )
                    if aggressive:
                        _replace_primary(aggressive)
                elif not is_a and not fav_a:
                    aggressive = _pick_from_crs(
                        crs, outcome="lose", min_goals=3, prefer=["1:2", "1:3", "0:3"],
                    )
                    if aggressive:
                        _replace_primary(aggressive)

            if must_win and pos >= 3 and gpg < 1.0:
                # 榜末抢分 → 更开放
                open_sec = _pick_from_crs(
                    crs, min_goals=2, exclude={picks[0]},
                    prefer=["2:1", "1:2", "1:1"],
                )
                if open_sec:
                    _replace_secondary(open_sec)

        # 当前进球率：进攻火热 → 略抬总进球
        sa = ctx.get("standing_a") or {}
        sb = ctx.get("standing_b") or {}
        avg_gf = float(ctx.get("group_avg_gf") or 1.35)
        if sa.get("played") and sb.get("played"):
            hot_a = sa["goals_for"] / sa["played"] >= avg_gf + 0.35
            hot_b = sb["goals_for"] / sb["played"] >= avg_gf + 0.35
            if hot_a and hot_b:
                hot = _pick_from_crs(crs, min_goals=3, prefer=["2:1", "1:2", "2:2"])
                if hot and _score_outcome(picks[0]) == _score_outcome(hot):
                    _replace_primary(hot)

    # ── 3. Knockout path pressure (出线后对手强度) ──
    for side, is_a in (("a", True), ("b", False)):
        pressure = float(ctx.get(f"path_pressure_{side}") or 0)
        band = ctx.get(f"finish_band_{side}", "")
        if pressure >= 0.45 and md == 3:
            if is_a and fav_a:
                win = _pick_from_crs(crs, outcome="win", prefer=["2:1", "2:0", "1:0"])
                if win:
                    _replace_primary(win)
            elif not is_a and not fav_a:
                win = _pick_from_crs(crs, outcome="lose", prefer=["1:2", "0:2", "0:1"])
                if win:
                    _replace_primary(win)
        elif band == "leading" and pressure < 0 and md == 3:
            tight = _pick_from_crs(crs, max_goals=2, prefer=["1:0", "0:1", "1:1"])
            if tight:
                _replace_secondary(tight)

    # De-dupe while preserving order
    out: list[str] = []
    for s in picks:
        if s and s not in out:
            out.append(s)
    return out[:2]
