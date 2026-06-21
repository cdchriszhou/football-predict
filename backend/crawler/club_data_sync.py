"""
Sync real五大联赛 data from football-data.org into DB.

Covers: fixtures (time/season/matchday/status/scores), standings, squads.
Falls back to existing seed + The Odds API when API key is missing.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from data.club_crests import crest_url_for
from data.club_name_map import resolve_club_cn
from data.competitions import get_competition
from data.match_status import cleanup_orphan_seed_matches
from data.status_constants import PLAYER_ACTIVE
from db.models import Match, Player, Team
from crawler.football_data_client import (
    fetch_competition_matches,
    fetch_standings,
    fetch_team_squad,
    map_match_status,
    map_player_position,
    player_age_from_dob,
    _api_key,
)
from utils.logger import logger


def _season_label(year: int) -> str:
    """2025 -> '2025/26'"""
    y = int(year)
    return f"{y}/{str(y + 1)[-2:]}"


def _ability_from_rank(rank: int, total: int) -> dict:
    pct = max(0, 1 - (rank - 1) / max(total - 1, 1))
    base = 62 + pct * 28
    return {
        "attack": round(base + pct * 6),
        "defend": round(base - (1 - pct) * 4),
        "midfield": round(base),
        "speed": round(base - 2),
        "physical": round(base - 1),
    }


async def sync_league_from_football_data(db: AsyncSession, slug: str) -> dict:
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return {"status": "skipped", "reason": "not_club"}

    if not _api_key():
        return {"status": "skipped", "reason": "no_football_data_api_key"}

    fd_code = comp.get("football_data_code")
    season_year = int(comp.get("season_year") or datetime.now().year)
    if not fd_code:
        return {"status": "skipped", "reason": "no_fd_code"}

    season_str = _season_label(season_year)
    matches_raw = await fetch_competition_matches(fd_code, season_year)
    standings = await fetch_standings(fd_code, season_year)

    if not matches_raw and not standings:
        return {"status": "empty", "reason": "football_data_empty"}

    teams_synced = await _sync_standings(db, slug, season_str, standings)
    sched = await _sync_fixtures(db, slug, season_str, comp.get("short_name", slug), matches_raw)
    squads = await _sync_squads(db, slug, max_teams=8)
    removed = await cleanup_orphan_seed_matches(db, slug)

    from data.league_standings import ensure_league_standings_stats
    await ensure_league_standings_stats(db, slug)

    await db.flush()
    return {
        "status": "success",
        "source": "football-data.org",
        "season": season_str,
        "teams": teams_synced,
        "schedule": sched,
        "squads": squads,
        "removed_orphans": removed,
    }


async def _sync_standings(
    db: AsyncSession, slug: str, season: str, standings: list[dict],
) -> int:
    if not standings:
        return 0
    total = len(standings)
    count = 0
    for row in standings:
        cn = resolve_club_cn(fd_id=row.get("fd_id"), name_en=row.get("name_en"))
        if not cn:
            continue
        rank = row.get("rank") or 0
        abilities = _ability_from_rank(rank, total)
        existing = (await db.execute(
            select(Team).where(
                Team.competition_slug == slug,
                Team.external_id == row.get("fd_id"),
            )
        )).scalar_one_or_none()
        if not existing:
            existing = (await db.execute(
                select(Team).where(Team.competition_slug == slug, Team.name == cn)
            )).scalar_one_or_none()

        en_name = row.get("name_en") or cn
        crest = crest_url_for(cn)
        if existing:
            existing.name = cn
            existing.name_en = en_name
            existing.rank = rank
            existing.season = season
            existing.external_id = row.get("fd_id")
            existing.points = row.get("points")
            existing.played = row.get("played")
            existing.won = row.get("won")
            existing.draw = row.get("draw")
            existing.lost = row.get("lost")
            existing.goals_for = row.get("goals_for")
            existing.goals_against = row.get("goals_against")
            if crest:
                existing.flag_url = crest
            for k, v in abilities.items():
                setattr(existing, k, v)
        else:
            db.add(Team(
                competition_slug=slug,
                name=cn,
                name_en=en_name,
                external_id=row.get("fd_id"),
                season=season,
                flag_url=crest or "",
                rank=rank,
                points=row.get("points"),
                played=row.get("played"),
                won=row.get("won"),
                draw=row.get("draw"),
                lost=row.get("lost"),
                goals_for=row.get("goals_for"),
                goals_against=row.get("goals_against"),
                tactic="联赛常规",
                price="-",
                group_name=None,
                **abilities,
            ))
        count += 1
    return count


async def _sync_fixtures(
    db: AsyncSession,
    slug: str,
    season: str,
    league_label: str,
    matches_raw: list[dict],
) -> dict:
    if not matches_raw:
        return {"created": 0, "updated": 0}

    existing = (await db.execute(
        select(Match).where(Match.competition_slug == slug)
    )).scalars().all()
    by_ext = {m.external_id: m for m in existing if m.external_id}
    by_key = {
        (m.team_a, m.team_b, m.match_time.date() if m.match_time else None): m
        for m in existing
    }

    created = updated = 0
    for row in matches_raw:
        home = resolve_club_cn(fd_id=row.get("home_id"), name_en=row.get("home_name_en"))
        away = resolve_club_cn(fd_id=row.get("away_id"), name_en=row.get("away_name_en"))
        kickoff = row.get("utc_date")
        if not home or not away or not kickoff:
            continue

        status = map_match_status(row.get("status_raw"))
        ra = row.get("result_a")
        rb = row.get("result_b")
        ext_id = row.get("external_id")
        matchday = row.get("matchday")
        venue = row.get("venue") or league_label
        stage = f"第{matchday}轮" if matchday else "联赛"

        current = by_ext.get(ext_id) if ext_id else None
        if not current:
            key = (home, away, kickoff.date())
            current = by_key.get(key)

        if current:
            current.team_a = home
            current.team_b = away
            current.match_time = kickoff
            current.status = status
            current.season = season
            current.matchday = matchday
            current.external_id = ext_id
            current.stage = stage
            current.location = league_label
            current.stadium = venue if isinstance(venue, str) else league_label
            if ra is not None and rb is not None:
                current.result_a = ra
                current.result_b = rb
            updated += 1
        else:
            db.add(Match(
                competition_slug=slug,
                stage=stage,
                group_name=None,
                team_a=home,
                team_b=away,
                match_time=kickoff,
                location=league_label,
                stadium=venue if isinstance(venue, str) else league_label,
                status=status,
                season=season,
                matchday=matchday,
                external_id=ext_id,
                result_a=ra if ra is not None else 0,
                result_b=rb if rb is not None else 0,
            ))
            created += 1

    return {"created": created, "updated": updated}


async def _sync_squads(db: AsyncSession, slug: str, max_teams: int = 8) -> dict:
    teams = (await db.execute(
        select(Team).where(
            Team.competition_slug == slug,
            Team.external_id.isnot(None),
        ).order_by(Team.rank.asc())
    )).scalars().all()

    synced = players = 0
    for team in teams[:max_teams]:
        detail = await fetch_team_squad(team.external_id)
        if not detail or not detail.get("squad"):
            continue
        await db.execute(delete(Player).where(Player.team_id == team.id))
        for p in detail["squad"]:
            pos = map_player_position(p.get("position"))
            number = p.get("shirt_number")
            try:
                number = int(number) if number is not None else None
            except (TypeError, ValueError):
                number = None
            age = player_age_from_dob(p.get("date_of_birth"))
            ability = 70 if pos == "GK" else 72
            if age:
                ability = max(60, min(88, 62 + max(0, 30 - abs(age - 26))))
            db.add(Player(
                team_id=team.id,
                name=p.get("name") or "",
                name_en=p.get("name_en"),
                position=pos,
                number=number,
                age=age,
                nationality=p.get("nationality"),
                status=PLAYER_ACTIVE,
                ability=ability,
                is_starter=1 if (number and number <= 11) else 0,
            ))
            players += 1
        synced += 1
    return {"teams": synced, "players": players}
