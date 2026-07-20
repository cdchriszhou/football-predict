"""World Cup group-stage standings and tournament-form context."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.status_constants import MATCH_FINISHED, match_status_in_db_values
from db.models import Match

DEFAULT_GROUP_AVG_GF = 1.35


def _parse_time(val: datetime | str | None) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    return None


@dataclass
class GroupTeamStanding:
    team: str
    played: int = 0
    won: int = 0
    draw: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def points(self) -> int:
        return self.won * 3 + self.draw

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["points"] = self.points
        d["goal_diff"] = self.goal_diff
        return d


def _apply_result(row: GroupTeamStanding, gf: int, ga: int) -> None:
    row.played += 1
    row.goals_for += gf
    row.goals_against += ga
    if gf > ga:
        row.won += 1
    elif gf < ga:
        row.lost += 1
    else:
        row.draw += 1


def compute_standings_from_rows(
    matches: list[dict],
    group_name: str,
    *,
    before_time: datetime | None = None,
) -> dict[str, GroupTeamStanding]:
    """Build standings from match dicts with team_a, team_b, result_a, result_b, group_name."""
    stats: dict[str, GroupTeamStanding] = {}

    def _row(name: str) -> GroupTeamStanding:
        if name not in stats:
            stats[name] = GroupTeamStanding(team=name)
        return stats[name]

    for m in matches:
        if m.get("stage") != "小组赛":
            continue
        if (m.get("group_name") or "") != group_name:
            continue
        ra, rb = m.get("result_a"), m.get("result_b")
        if ra is None or rb is None:
            continue
        mt = _parse_time(m.get("match_time"))
        cutoff = _parse_time(before_time)
        if cutoff and mt and mt >= cutoff:
            continue

        ta, tb = m["team_a"], m["team_b"]
        _apply_result(_row(ta), int(ra), int(rb))
        _apply_result(_row(tb), int(rb), int(ra))

    return stats


def rank_standings(standings: dict[str, GroupTeamStanding]) -> list[GroupTeamStanding]:
    return sorted(
        standings.values(),
        key=lambda s: (s.points, s.goal_diff, s.goals_for, s.team),
        reverse=True,
    )


def group_avg_goals_for(standings: dict[str, GroupTeamStanding]) -> float:
    total_gf = sum(s.goals_for for s in standings.values())
    total_played = sum(s.played for s in standings.values())
    if total_played == 0:
        return DEFAULT_GROUP_AVG_GF
    return total_gf / total_played


def _attack_form_delta(standing: GroupTeamStanding | None, avg_gf: float) -> float:
    if not standing or standing.played == 0:
        return 0.0
    gpg = standing.goals_for / standing.played
    return max(-0.25, min(0.25, (gpg - avg_gf) * 0.15))


def _defense_leak_delta(standing: GroupTeamStanding | None, avg_gf: float) -> float:
    """Extra goals conceded per game vs group average (boosts opponent xG)."""
    if not standing or standing.played == 0:
        return 0.0
    gaa = standing.goals_against / standing.played
    return max(-0.15, min(0.15, (gaa - avg_gf) * 0.10))


def apply_form_to_expected_goals(
    expected_a: float,
    expected_b: float,
    standing_a: GroupTeamStanding | None,
    standing_b: GroupTeamStanding | None,
    avg_gf: float,
    matchday: int,
) -> tuple[float, float]:
    if matchday < 2:
        return expected_a, expected_b
    form_a = _attack_form_delta(standing_a, avg_gf)
    form_b = _attack_form_delta(standing_b, avg_gf)
    leak_a = _defense_leak_delta(standing_a, avg_gf)
    leak_b = _defense_leak_delta(standing_b, avg_gf)
    return (
        max(0.15, expected_a + form_a + leak_b),
        max(0.15, expected_b + form_b + leak_a),
    )


def _motivation_from_standing(
    standing: GroupTeamStanding | None,
    matchday: int,
) -> tuple[bool, bool, bool]:
    """Return (must_win, qualified_comfortable, need_goals)."""
    if not standing or standing.played == 0 or matchday < 2:
        return False, False, False

    pts, played = standing.points, standing.played
    must_win = False
    qualified = False
    need_goals = False

    if matchday == 2 and played >= 1:
        if pts == 0:
            must_win = True
        elif pts >= 3:
            qualified = True
        elif pts == 1:
            must_win = True

    if matchday == 3 and played >= 2:
        if pts <= 1:
            must_win = True
        elif pts >= 6:
            qualified = True
        elif pts >= 4 and standing.goal_diff >= 0:
            qualified = True
        elif pts == 3 and standing.goal_diff < 0:
            must_win = True
            need_goals = True
        elif pts == 4 and standing.goal_diff <= -2:
            need_goals = True

    return must_win, qualified, need_goals


def enrich_group_context(
    ctx: dict,
    team_a: str,
    team_b: str,
    standings: dict[str, GroupTeamStanding] | None,
    matchday: int,
) -> dict:
    """Fill motivation + tournament form fields on group_context."""
    if not standings or matchday < 2:
        ctx.setdefault("form_xg_a", 0.0)
        ctx.setdefault("form_xg_b", 0.0)
        return ctx

    sa = standings.get(team_a)
    sb = standings.get(team_b)
    avg_gf = group_avg_goals_for(standings)
    ranked = rank_standings(standings)

    ctx["group_avg_gf"] = round(avg_gf, 2)
    ctx["standing_a"] = sa.to_dict() if sa else None
    ctx["standing_b"] = sb.to_dict() if sb else None
    ctx["group_table"] = [s.to_dict() for s in ranked]

    mw_a, qual_a, ng_a = _motivation_from_standing(sa, matchday)
    mw_b, qual_b, ng_b = _motivation_from_standing(sb, matchday)

    ctx["must_win_a"] = mw_a
    ctx["must_win_b"] = mw_b
    ctx["qualified_a"] = qual_a
    ctx["qualified_b"] = qual_b
    ctx["need_goals_a"] = ng_a
    ctx["need_goals_b"] = ng_b

    ctx["form_xg_a"] = _attack_form_delta(sa, avg_gf)
    ctx["form_xg_b"] = _attack_form_delta(sb, avg_gf)
    ctx["defense_leak_a"] = _defense_leak_delta(sa, avg_gf)
    ctx["defense_leak_b"] = _defense_leak_delta(sb, avg_gf)

    if matchday == 3 and sa and sb and sa.played >= 2 and sb.played >= 2:
        if mw_a and mw_b:
            ctx["both_must_win"] = True
            ctx["both_need_draw"] = False
        elif sa.points == sb.points and sa.points >= 3:
            if sa.goal_diff > sb.goal_diff:
                ctx["draw_suits_a"] = True
                ctx["must_win_b"] = True
            elif sb.goal_diff > sa.goal_diff:
                ctx["draw_suits_b"] = True
                ctx["must_win_a"] = True
            else:
                ctx["both_need_draw"] = True
        elif (
            abs(sa.points - sb.points) <= 1
            and sa.points >= 3
            and sb.points >= 3
            and qual_a
            and qual_b
            and not mw_a
            and not mw_b
        ):
            ctx["both_need_draw"] = True

    return ctx


def format_group_situation(
    ctx: dict,
    team_a: str,
    team_b: str,
) -> str:
    """Human-readable group situation for LLM prompt."""
    if ctx.get("matchday", 0) < 2:
        return ""

    lines = [f"【小组形势 — 第{ctx.get('matchday')}轮】"]
    table = ctx.get("group_table") or []
    if table:
        rows = []
        for i, row in enumerate(table, 1):
            rows.append(
                f"  {i}. {row['team']} {row['points']}分 "
                f"({row['won']}胜{row['draw']}平{row['lost']}负 "
                f"进{row['goals_for']}失{row['goals_against']})"
            )
        lines.append("积分榜（赛前）：")
        lines.extend(rows)

    def _team_line(name: str, side: str) -> None:
        st = ctx.get(f"standing_{side}")
        if not st:
            return
        notes = []
        if ctx.get(f"must_win_{side}"):
            notes.append("必须抢分")
        if ctx.get(f"qualified_{side}"):
            notes.append("首战/积分形势较好，可接受平局")
        if ctx.get(f"need_goals_{side}"):
            notes.append("需提升净胜球")
        if notes:
            lines.append(f"  {name}：{st['points']}分 — {'；'.join(notes)}")

    _team_line(team_a, "a")
    _team_line(team_b, "b")

    sa = ctx.get("standing_a") or {}
    sb = ctx.get("standing_b") or {}
    if sa.get("played") and sb.get("played"):
        lines.append(
            f"  首战进球率：{team_a} {sa['goals_for']}/{sa['played']}球，"
            f"{team_b} {sb['goals_for']}/{sb['played']}球"
        )

    if ctx.get("both_need_draw"):
        lines.append("  ⚠ 末轮积分接近，存在默契平局可能")

    note = ctx.get("knockout_outlook_note")
    if note:
        lines.append(f"  出线形势：{note}")

    return "\n".join(lines) + "\n"


async def load_group_standings(
    db: AsyncSession,
    competition_slug: str,
    group_name: str,
    before_time: datetime,
) -> dict[str, GroupTeamStanding]:
    """Load group standings from finished matches before kickoff."""
    finished = match_status_in_db_values(MATCH_FINISHED)
    rows = (await db.execute(
        select(Match).where(
            Match.competition_slug == competition_slug,
            Match.stage == "小组赛",
            Match.group_name == group_name,
            Match.status.in_(finished),
            Match.result_a.isnot(None),
            Match.result_b.isnot(None),
            Match.match_time < before_time,
        )
    )).scalars().all()

    matches = [
        {
            "stage": m.stage,
            "group_name": m.group_name,
            "team_a": m.team_a,
            "team_b": m.team_b,
            "result_a": m.result_a,
            "result_b": m.result_b,
            "match_time": m.match_time,
        }
        for m in rows
    ]
    return compute_standings_from_rows(matches, group_name, before_time=before_time)


def load_standings_from_history(
    historical: list[dict],
    group_name: str,
    before_time: datetime | None = None,
) -> dict[str, GroupTeamStanding]:
    """Standings for backtest from worldcup_history rows."""
    return compute_standings_from_rows(historical, group_name, before_time=before_time)


async def load_group_fifa_ranks(
    db: AsyncSession,
    competition_slug: str,
    group_name: str,
) -> list[int]:
    """FIFA ranks for all teams in a group (for knockout path estimation)."""
    from db.models import Team
    from crawler.team_crawler import GROUPS

    letter = (group_name or "").strip().upper()
    names = GROUPS.get(letter) or []
    if not names:
        rows = (await db.execute(
            select(Team.name, Team.rank).where(
                Team.competition_slug == competition_slug,
                Team.group_name == group_name,
            )
        )).all()
        return sorted(int(r or 50) for _, r in rows)

    ranks: list[int] = []
    for name in names:
        row = (await db.execute(
            select(Team.rank).where(
                Team.competition_slug == competition_slug,
                Team.name == name,
            )
        )).scalar_one_or_none()
        ranks.append(int(row or 50))
    return sorted(ranks)
