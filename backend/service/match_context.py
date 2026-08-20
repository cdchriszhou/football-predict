"""
Match context analysis: upsets, collusion (默契球), motivation, market manipulation.

Detects situational factors that standard strength models miss.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from service.league_rank import (
    GAP_CLEAR,
    GAP_LARGE,
    GAP_MISMATCH,
    MINNOW_RANK,
    rank_gap as league_rank_gap,
    table_rank,
)


@dataclass
class ContextAnalysis:
    upset_risk: float = 0.0          # 0-1 probability boost for underdog
    collusion_risk: float = 0.0      # 0-1 draw probability boost
    manipulation_risk: float = 0.0   # 0-1 market anomaly weight
    draw_adjustment: float = 0.0     # percentage points to add to draw
    favourite_lose_shift: float = 0.0  # shift mass from away fav to draw (minnow home)
    underdog_side: str = ""          # "a" / "b" / ""
    confidence_penalty: float = 0.0  # reduce prediction confidence
    alerts: list = field(default_factory=list)
    group_context: dict = field(default_factory=dict)


def infer_matchday(stage: str, group_name: str, match_time=None) -> int:
    """World Cup group MD1-3 inference retired; league matchday comes from the caller."""
    return 0


def _is_league_matchday(stage: str | None) -> bool:
    s = (stage or "").strip()
    if s in ("联赛",):
        return True
    return s.startswith("第") and s.endswith("轮")


def build_group_context(
    stage: str,
    group_name: str = "",
    matchday: int = 0,
    team_a: str = "",
    team_b: str = "",
    rank_a: int | None = None,
    rank_b: int | None = None,
    location: str = "",
    standings: dict | None = None,
    home_side_override: str | None = None,
) -> dict:
    """Build league / group context for the rule engine.

    For club leagues, pass home_side_override='a' (team_a is always home in sync)
    and a name→standing map from load_club_standings_map().
    """
    if home_side_override in ("a", "b"):
        home_side = home_side_override
    else:
        home_side = ""
    is_group_opener = stage == "小组赛" and matchday == 1 and bool(home_side)
    # Club fixtures pass home_side_override even when stage is blank / "联赛".
    is_league = _is_league_matchday(stage) or home_side_override in ("a", "b")
    home_win_boost = 0.0
    home_xg_boost = 0.0
    if home_side:
        if is_league:
            home_win_boost = 5.0
            home_xg_boost = 0.35
        else:
            home_win_boost = 6.0 if is_group_opener else 4.0
            home_xg_boost = 0.55 if is_group_opener else 0.28

    ra = table_rank(rank_a)
    rb = table_rank(rank_b)
    ctx = {
        "stage": stage,
        "group_name": group_name,
        "matchday": matchday,
        "location": location,
        "home_side": home_side,
        "home_win_boost": home_win_boost,
        "home_xg_boost": home_xg_boost,
        "is_group_opener": is_group_opener,
        "must_win_a": False,
        "must_win_b": False,
        "qualified_a": False,
        "qualified_b": False,
        "both_need_draw": False,
        "both_must_win": False,
        "draw_suits_a": False,
        "draw_suits_b": False,
        "dead_rubber": False,
        "is_final_group_match": False,
        "need_goals_a": False,
        "need_goals_b": False,
        "form_xg_a": 0.0,
        "form_xg_b": 0.0,
        "defense_leak_a": 0.0,
        "defense_leak_b": 0.0,
        "rank_a": ra,
        "rank_b": rb,
        "rank_gap": league_rank_gap(ra, rb),
        "is_league": is_league,
        # MD1–6: table ranks are noisy; prefer ability + markets over live table.
        "early_season": bool(is_league and matchday > 0 and matchday < 7),
    }
    if is_league and standings:
        _apply_league_table_motivation(ctx, team_a, team_b, standings)
    return ctx


def _standing_row(standings: dict, name: str) -> dict | None:
    if not standings or not name:
        return None
    row = standings.get(name)
    if isinstance(row, dict) and not name.startswith("_"):
        return row
    return None


def _apply_league_table_motivation(
    ctx: dict,
    team_a: str,
    team_b: str,
    standings: dict,
) -> None:
    """Title race / relegation / dead-rubber flags from the current table."""
    sa = _standing_row(standings, team_a)
    sb = _standing_row(standings, team_b)
    if not sa or not sb:
        return

    ctx["standing_a"] = sa
    ctx["standing_b"] = sb
    size = int(standings.get("_size") or 0) or 20
    ctx["table_size"] = size

    ra = table_rank(sa.get("rank"))
    rb = table_rank(sb.get("rank"))
    if ra is None or rb is None:
        return
    pa = int(sa.get("points") or 0)
    pb = int(sb.get("points") or 0)
    played = min(int(sa.get("played") or 0), int(sb.get("played") or 0))
    md = int(ctx.get("matchday") or 0)

    # Table is noisy until both sides have a handful of games.
    if played < 6 and md < 8:
        return

    title_cut = 4
    releg_cut = max(title_cut + 1, size - 2)
    late = md >= 30 or played >= 30
    very_late = md >= 34 or played >= 34

    in_title_a = ra <= title_cut
    in_title_b = rb <= title_cut
    in_releg_a = ra >= releg_cut
    in_releg_b = rb >= releg_cut

    if in_title_a and in_title_b and abs(pa - pb) <= 6:
        ctx["both_must_win"] = True
        ctx["need_goals_a"] = True
        ctx["need_goals_b"] = True
    if in_releg_a and in_releg_b:
        ctx["both_must_win"] = True
        ctx["must_win_a"] = True
        ctx["must_win_b"] = True

    if late:
        if in_releg_a and not in_releg_b:
            ctx["must_win_a"] = True
        if in_releg_b and not in_releg_a:
            ctx["must_win_b"] = True
        if in_title_a and not in_title_b and ra <= 2:
            ctx["must_win_a"] = True
        if in_title_b and not in_title_a and rb <= 2:
            ctx["must_win_b"] = True

    mid_a = 6 <= ra <= size - 5
    mid_b = 6 <= rb <= size - 5
    if very_late and mid_a and mid_b and not ctx["both_must_win"]:
        ctx["dead_rubber"] = True


def analyze_match_context(
    team_a: dict,
    team_b: dict,
    group_context: dict = None,
    market_signals: dict = None,
    fundamentals: dict = None,
) -> ContextAnalysis:
    """Comprehensive situational analysis for a single match."""
    ctx = group_context or {}
    market = market_signals or {}
    fund = fundamentals or {}
    result = ContextAnalysis(group_context=ctx)

    rank_a = table_rank(team_a.get("rank"))
    rank_b = table_rank(team_b.get("rank"))
    rank_gap = league_rank_gap(rank_a, rank_b)
    ra = rank_a if rank_a is not None else 10
    rb = rank_b if rank_b is not None else 10

    fund_win = fund.get("win_pct", 50.0)
    market_win = fund.get("market_win_pct", 50.0)

    # ── Upset detection (冷门) — league 1–20 table, not FIFA 1–200 ──
    fav_is_a = ra < rb
    underdog = "b" if fav_is_a else "a"
    home_side = ctx.get("home_side", "")
    fav_at_home = (
        home_side == "a" and fav_is_a
    ) or (
        home_side == "b" and not fav_is_a
    )

    if rank_gap >= GAP_CLEAR:
        base_upset = 0.10 + min(0.16, rank_gap / 40)
        if market_win > fund_win + 12:
            base_upset += 0.10
            result.alerts.append("市场热度高于实力：强队存在翻车风险")
        if market.get("shallow_handicap_trap"):
            base_upset += 0.12
        if ctx.get("is_final_group_match") and (
            ctx.get("qualified_a") or ctx.get("qualified_b")
        ):
            base_upset += 0.08
            result.alerts.append("出线队末轮可能轮换：冷门概率上升")
        if fav_at_home:
            base_upset = max(0.06, base_upset - 0.10)
            if ctx.get("is_group_opener"):
                base_upset = max(0.05, base_upset - 0.08)
                result.alerts.append("东道主揭幕战主场作战：适度降低冷门权重")
        if rank_gap >= GAP_MISMATCH and fav_at_home:
            base_upset = min(base_upset, 0.12)
        result.upset_risk = min(0.38, base_upset)
        result.underdog_side = underdog if fav_is_a else ("a" if rb < ra else "")

    # Knockout underdog with defensive style (not club league matchdays)
    stage = ctx.get("stage", "")
    from service.score_pick import is_knockout_stage
    if is_knockout_stage(stage) and rank_gap >= GAP_CLEAR:
        def_style = team_b.get("tactic", "") if ra < rb else team_a.get("tactic", "")
        if any(t in def_style for t in ("防守", "防反", "铁桶", "硬朗")):
            result.upset_risk = min(0.40, result.upset_risk + 0.08)
            result.alerts.append("淘汰赛防守型弱队：拖入加时/点球概率高")

    # ── Collusion detection (默契球) — World Cup group MD3 only, not league round 3 ──
    if ctx.get("stage") == "小组赛" and (ctx.get("is_final_group_match") or ctx.get("matchday") == 3):
        collusion = 0.15   # was 0.10 — higher baseline for 2026 draw rate
        if ctx.get("both_must_win"):
            collusion = 0.04
        elif ctx.get("both_need_draw"):
            collusion += 0.18
            result.alerts.append("小组赛末轮实力接近：存在默契平局可能")
        elif ctx.get("draw_suits_a") or ctx.get("draw_suits_b"):
            collusion += 0.06
            result.alerts.append("末轮同分：领先方可接受平局，落后方需抢胜")
        if ctx.get("must_win_a") or ctx.get("must_win_b"):
            collusion = max(0.04, collusion - 0.14)
        if market.get("draw_protection"):
            collusion += 0.15
            result.alerts.append("盘口平赔保护：庄家防范默契平局")
        imp_draw = fund.get("market_draw_pct", 0)
        if imp_draw > 30:
            collusion += 0.08
        result.collusion_risk = min(0.55, collusion)   # was 0.50
        result.draw_adjustment += result.collusion_risk * 10

    if ctx.get("dead_rubber"):
        result.collusion_risk = max(result.collusion_risk, 0.25)
        result.draw_adjustment += 5
        result.alerts.append("无关痛痒之战：双方无进攻动力")

    # ── League table motivation (title / relegation) ──
    if _is_league_matchday(stage):
        name_a = team_a.get("name", "")
        name_b = team_b.get("name", "")
        if ctx.get("both_must_win") or ctx.get("must_win_a") or ctx.get("must_win_b"):
            result.draw_adjustment -= 5.0
            if ctx.get("must_win_a"):
                result.alerts.append(f"{name_a} 联赛积分形势需抢分，平局权重下调")
            if ctx.get("must_win_b"):
                result.alerts.append(f"{name_b} 联赛积分形势需抢分，平局权重下调")
            if ctx.get("both_must_win") and not (ctx.get("must_win_a") or ctx.get("must_win_b")):
                result.alerts.append("联赛六分之战：双方都需要胜场")
        if ctx.get("need_goals_a"):
            result.alerts.append(f"{name_a} 净胜球/积分落后，可能加强进攻")
        if ctx.get("need_goals_b"):
            result.alerts.append(f"{name_b} 净胜球/积分落后，可能加强进攻")

    # ── Group-stage motivation (round 2+) ──
    if ctx.get("stage") == "小组赛" and ctx.get("matchday", 0) >= 2:
        name_a = team_a.get("name", "")
        name_b = team_b.get("name", "")
        sa = ctx.get("standing_a") or {}
        sb = ctx.get("standing_b") or {}
        fav_is_a = ra < rb
        opp_st = sb if fav_is_a else sa
        fav_st = sa if fav_is_a else sb
        def_team = team_b if fav_is_a else team_a

        if opp_st.get("played") and opp_st.get("goals_against") == 0:
            result.draw_adjustment += 10.0
            result.upset_risk = min(0.38, result.upset_risk + 0.10)
            result.alerts.append(f"对手{('B' if fav_is_a else 'A')}队首轮零封：热门破门难度上调")

        if fav_st.get("played") and fav_st.get("goals_for", 0) / max(1, fav_st["played"]) <= 1.0:
            result.draw_adjustment += 6.0
            result.alerts.append(f"{'A' if fav_is_a else 'B'}队首轮进球偏少：闷平概率上升")

        if any(t in def_team.get("tactic", "") for t in ("铁桶", "防守", "防反", "硬朗")):
            if rank_gap >= 8:
                result.draw_adjustment += 5.0
                result.upset_risk = min(0.38, result.upset_risk + 0.06)

        if ctx.get("must_win_a"):
            result.draw_adjustment = max(0.0, result.draw_adjustment - 4.0)
            result.alerts.append(f"{name_a} 小组赛需抢分，平局权重下调")
        if ctx.get("must_win_b"):
            result.draw_adjustment = max(0.0, result.draw_adjustment - 4.0)
            result.alerts.append(f"{name_b} 小组赛需抢分，平局权重下调")
        if ctx.get("qualified_a"):
            result.draw_adjustment += 3.0
            result.alerts.append(f"{name_a} 积分形势较好，可接受小胜或平局")
        if ctx.get("qualified_b"):
            result.draw_adjustment += 3.0
            result.alerts.append(f"{name_b} 积分形势较好，可接受小胜或平局")
        if ctx.get("need_goals_a"):
            result.alerts.append(f"{name_a} 净胜球落后，可能加强进攻")
        if ctx.get("need_goals_b"):
            result.alerts.append(f"{name_b} 净胜球落后，可能加强进攻")

    # Weak home side vs away favourite — park-the-bus (league relegation zone)
    home_rank = ra if home_side != "b" else rb
    away_rank = rb if home_side != "b" else ra
    if (
        _is_league_matchday(stage)
        and home_rank >= MINNOW_RANK
        and away_rank <= 6
        and rank_gap >= GAP_LARGE
        and not fav_at_home
    ):
        result.draw_adjustment += 6.0
        result.favourite_lose_shift = 0.12
        result.upset_risk = min(0.38, result.upset_risk + 0.05)
        result.alerts.append("保级队主场守平：平局权重上调")

    # ── Market manipulation (资本/盘口操控) ──
    result.manipulation_risk = market.get("manipulation_risk", 0.0)
    if market.get("euro_macau_divergence", 0) > 10:
        result.confidence_penalty += 0.08
        result.alerts.append("欧澳盘口分歧显著：预测置信度下调")
    if result.manipulation_risk > 0.3:
        result.confidence_penalty += 0.10
        result.alerts.append("检测到异常盘口信号：谨慎参考")

    result.upset_risk = round(min(0.38, result.upset_risk), 2)
    result.collusion_risk = round(result.collusion_risk, 2)
    result.draw_adjustment = round(result.draw_adjustment, 1)
    result.confidence_penalty = round(result.confidence_penalty, 2)
    return result


def apply_context_to_rates(
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    context: ContextAnalysis,
) -> tuple[float, float, float]:
    """Apply upset/collusion adjustments to W/D/L rates."""
    w, d, l = win_rate, draw_rate, lose_rate

    # Collusion → boost draw
    d = min(38.0, d + context.draw_adjustment)
    if context.favourite_lose_shift > 0 and l > w:
        take = min(l - 12.0, context.favourite_lose_shift * 100)
        if take > 0:
            l -= take
            d = min(38.0, d + take)
    remaining = 100.0 - d
    wl = w + l
    if wl > 0:
        w = remaining * w / wl
        l = remaining * l / wl

    # Upset → shift from favorite to underdog
    if context.upset_risk > 0 and context.underdog_side:
        shift = context.upset_risk * 15
        if context.underdog_side == "a" and w < l:
            w, l = min(w + shift, remaining - 5), max(l - shift, 5)
        elif context.underdog_side == "b" and l < w:
            l, w = min(l + shift, remaining - 5), max(w - shift, 5)
        elif context.underdog_side == "a":
            w, l = min(w + shift, remaining - 5), max(l - shift, 5)
        else:
            l, w = min(l + shift, remaining - 5), max(w - shift, 5)
        total = w + d + l
        if abs(total - 100) > 0.5:
            scale = 100 / total
            w, d, l = w * scale, d * scale, l * scale

    return round(w, 1), round(d, 1), round(l, 1)
