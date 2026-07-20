"""Compute league standings from finished matches when API stats are missing."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.competitions import get_competition
from data.match_status import season_label_for
from data.status_constants import MATCH_FINISHED, match_status_in_db_values
from db.models import Match, Team


@dataclass
class _Row:
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


def _apply_result(row: _Row, goals_for: int, goals_against: int) -> None:
    row.played += 1
    row.goals_for += goals_for
    row.goals_against += goals_against
    if goals_for > goals_against:
        row.won += 1
    elif goals_for < goals_against:
        row.lost += 1
    else:
        row.draw += 1


async def recompute_standings_from_matches(
    db: AsyncSession,
    slug: str,
    season: str | None = None,
) -> int:
    """
    Derive played/won/draw/lost/goals/points from finished league matches
    and persist to Team rows. Returns number of teams updated.
    """
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return 0

    season = season or season_label_for(comp)
    finished = match_status_in_db_values(MATCH_FINISHED)

    match_filters = [Match.competition_slug == slug, Match.status.in_(finished)]
    if season:
        match_filters.append(Match.season == season)

    matches = (await db.execute(select(Match).where(*match_filters))).scalars().all()
    if not matches:
        return 0

    team_filters = [Team.competition_slug == slug]
    if season:
        team_filters.append(Team.season == season)
    teams = (await db.execute(select(Team).where(*team_filters))).scalars().all()
    if not teams:
        teams = (await db.execute(
            select(Team).where(Team.competition_slug == slug)
        )).scalars().all()

    by_name: dict[str, Team] = {t.name: t for t in teams}
    stats: dict[str, _Row] = {name: _Row() for name in by_name}

    for m in matches:
        ra, rb = m.result_a, m.result_b
        if ra is None or rb is None:
            continue
        for name, gf, ga in ((m.team_a, ra, rb), (m.team_b, rb, ra)):
            if name not in stats:
                stats[name] = _Row()
            _apply_result(stats[name], gf, ga)

    ranked = sorted(
        [(name, row) for name, row in stats.items() if row.played > 0],
        key=lambda x: (x[1].points, x[1].goal_diff, x[1].goals_for, x[0]),
        reverse=True,
    )

    updated = 0
    for rank, (name, row) in enumerate(ranked, start=1):
        team = by_name.get(name)
        if not team:
            continue
        team.rank = rank
        team.played = row.played
        team.won = row.won
        team.draw = row.draw
        team.lost = row.lost
        team.goals_for = row.goals_for
        team.goals_against = row.goals_against
        team.points = row.points
        if season and not team.season:
            team.season = season
        updated += 1

    if updated:
        await db.flush()
    return updated


async def ensure_league_standings_stats(
    db: AsyncSession,
    slug: str,
) -> int:
    """Recompute from matches when teams lack points but finished games exist."""
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return 0

    season = season_label_for(comp)
    filters = [Team.competition_slug == slug, Team.rank > 0]
    if season:
        filters.append(Team.season == season)
    teams = (await db.execute(select(Team).where(*filters))).scalars().all()
    if not teams:
        return 0

    needs = any(t.points is None or t.played is None for t in teams)
    if not needs:
        return 0

    return await recompute_standings_from_matches(db, slug, season)
