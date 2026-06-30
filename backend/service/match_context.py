"""
Match context analysis: upsets, collusion (默契球), motivation, market manipulation.

Detects situational factors that standard strength models miss.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 2026 World Cup co-hosts
HOST_NATIONS_2026 = frozenset({"墨西哥", "美国", "加拿大"})

_HOST_LOCATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "墨西哥": ("墨西哥", "墨西哥城", "萨波潘", "蒙特雷", "阿兹特克", "阿克伦", "BBVA"),
    "美国": (
        "纽约", "新泽西", "洛杉矶", "英格尔伍德", "波士顿", "费城", "迈阿密", "亚特兰大",
        "达拉斯", "休斯顿", "堪萨斯", "西雅图", "旧金山", "索菲", "李维斯",
        "流明", "大都会", "吉列", "林肯金融", "硬石", "梅赛德斯", "AT&T", "NRG", "箭头",
    ),
    "加拿大": ("多伦多", "温哥华", "蒙特利尔", "BMO", "卑诗"),
}


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
    """Infer group matchday (1/2/3) from stage label."""
    if stage != "小组赛":
        return 0
    return 0  # filled by caller when available


def detect_home_side(team_a: str, team_b: str, location: str = "") -> str:
    """Return 'a' / 'b' when a 2026 host plays in its home country venue."""
    loc = location or ""
    if not loc:
        return ""
    for side, name in (("a", team_a), ("b", team_b)):
        if name not in HOST_NATIONS_2026:
            continue
        for kw in _HOST_LOCATION_KEYWORDS.get(name, ()):
            if kw in loc:
                return side
    return ""


def build_group_context(
    stage: str,
    group_name: str = "",
    matchday: int = 0,
    team_a: str = "",
    team_b: str = "",
    rank_a: int = 50,
    rank_b: int = 50,
    location: str = "",
    standings: dict | None = None,
) -> dict:
    """Build group-stage context for rule engine."""
    home_side = detect_home_side(team_a, team_b, location)
    is_group_opener = stage == "小组赛" and matchday == 1 and bool(home_side)
    home_win_boost = 0.0
    home_xg_boost = 0.0
    if home_side:
        home_win_boost = 6.0 if is_group_opener else 4.0
        home_xg_boost = 0.55 if is_group_opener else 0.28

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
        "is_final_group_match": matchday == 3,
        "need_goals_a": False,
        "need_goals_b": False,
        "form_xg_a": 0.0,
        "form_xg_b": 0.0,
        "defense_leak_a": 0.0,
        "defense_leak_b": 0.0,
        "rank_a": rank_a,
        "rank_b": rank_b,
        "rank_gap": abs(rank_a - rank_b),
    }

    if stage == "小组赛" and standings and matchday >= 2:
        from data.worldcup_group_standings import enrich_group_context
        enrich_group_context(ctx, team_a, team_b, standings, matchday)
        return ctx

    if stage != "小组赛" or matchday < 3:
        return ctx

    # Round 3 fallback when no live standings: rank-based heuristics
    rank_gap = abs(rank_a - rank_b)
    if rank_gap <= 15:
        ctx["both_need_draw"] = True
    if rank_gap >= 40:
        ctx["qualified_a"] = rank_a < rank_b and rank_a <= 20
        ctx["qualified_b"] = rank_b < rank_a and rank_b <= 20

    return ctx


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

    rank_a = team_a.get("rank", 50) or 50
    rank_b = team_b.get("rank", 50) or 50
    rank_gap = abs(rank_a - rank_b)

    fund_win = fund.get("win_pct", 50.0)
    market_win = fund.get("market_win_pct", 50.0)

    # ── Upset detection (冷门) ──
    fav_is_a = rank_a < rank_b
    underdog = "b" if fav_is_a else "a"
    home_side = ctx.get("home_side", "")
    fav_at_home = (
        home_side == "a" and fav_is_a
    ) or (
        home_side == "b" and not fav_is_a
    )

    if rank_gap >= 20:
        # Historical WC: ~25% of 20+ rank-gap group games are upsets or draws
        base_upset = 0.12 + min(0.18, rank_gap / 200)
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
        # Host favorite at home: opener curse already priced in market, reduce cold risk
        if fav_at_home:
            base_upset = max(0.06, base_upset - 0.14)
            if ctx.get("is_group_opener"):
                base_upset = max(0.05, base_upset - 0.08)
                result.alerts.append("东道主揭幕战主场作战：适度降低冷门权重")
        if rank_gap >= 35 and fav_at_home:
            base_upset = min(base_upset, 0.12)
        result.upset_risk = min(0.38, base_upset)
        result.underdog_side = underdog if fav_is_a else ("a" if rank_b < rank_a else "")

    # Knockout underdog with defensive style
    stage = ctx.get("stage", "")
    if stage not in ("", "小组赛") and rank_gap >= 10:
        def_style = team_b.get("tactic", "") if rank_a < rank_b else team_a.get("tactic", "")
        if any(t in def_style for t in ("防守", "防反", "铁桶", "硬朗")):
            result.upset_risk = min(0.40, result.upset_risk + 0.08)
            result.alerts.append("淘汰赛防守型弱队：拖入加时/点球概率高")

    # ── Collusion detection (默契球) ──
    if ctx.get("is_final_group_match") or ctx.get("matchday") == 3:
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

    # ── Group-stage motivation (round 2+) ──
    if ctx.get("stage") == "小组赛" and ctx.get("matchday", 0) >= 2:
        name_a = team_a.get("name", "")
        name_b = team_b.get("name", "")
        sa = ctx.get("standing_a") or {}
        sb = ctx.get("standing_b") or {}
        fav_is_a = rank_a < rank_b
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

    # Minnow home vs away favourite — park-the-bus draw (Curacao 0:0 Ecuador)
    home_rank = rank_a if home_side != "b" else rank_b
    away_rank = rank_b if home_side != "b" else rank_a
    if (
        ctx.get("stage") == "小组赛"
        and ctx.get("matchday", 0) >= 2
        and home_rank >= 75
        and away_rank <= 35
        and rank_gap >= 35
        and not fav_at_home
    ):
        result.draw_adjustment += 14.0
        result.favourite_lose_shift = 0.26
        result.upset_risk = min(0.38, result.upset_risk + 0.06)
        result.alerts.append("弱队主场守平：平局与闷平比分权重上调")

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
