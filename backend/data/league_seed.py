"""Seed teams & fixtures for五大联赛 when live API data is unavailable."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from data.competitions import get_competition
from data.competition_status import _parse_iso
from data.club_crests import crest_url_for
from data.status_constants import (
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_UPCOMING,
    PLAYER_ACTIVE,
)
from data.match_status import season_label_for
from db.models import Match, Team

# slug -> list of (cn_name, en_name, rank_hint 1-based)
LEAGUE_TEAMS: dict[str, list[tuple[str, str, int]]] = {
    "premier-league": [
        ("曼城", "Manchester City", 1),
        ("阿森纳", "Arsenal", 2),
        ("利物浦", "Liverpool", 3),
        ("切尔西", "Chelsea", 4),
        ("曼联", "Manchester United", 5),
        ("热刺", "Tottenham Hotspur", 6),
        ("纽卡斯尔联", "Newcastle United", 7),
        ("阿斯顿维拉", "Aston Villa", 8),
        ("布莱顿", "Brighton", 9),
        ("西汉姆联", "West Ham United", 10),
        ("水晶宫", "Crystal Palace", 11),
        ("富勒姆", "Fulham", 12),
        ("狼队", "Wolverhampton", 13),
        ("埃弗顿", "Everton", 14),
        ("诺丁汉森林", "Nottingham Forest", 15),
        ("伯恩茅斯", "AFC Bournemouth", 16),
        ("布伦特福德", "Brentford", 17),
        ("莱斯特城", "Leicester City", 18),
        ("伊普斯维奇", "Ipswich Town", 19),
        ("南安普敦", "Southampton", 20),
    ],
    "la-liga": [
        ("皇马", "Real Madrid", 1),
        ("巴萨", "Barcelona", 2),
        ("马竞", "Atletico Madrid", 3),
        ("赫罗纳", "Girona", 4),
        ("毕尔巴鄂", "Athletic Bilbao", 5),
        ("皇家社会", "Real Sociedad", 6),
        ("贝蒂斯", "Real Betis", 7),
        ("比利亚雷亚尔", "Villarreal", 8),
        ("瓦伦西亚", "Valencia", 9),
        ("塞维利亚", "Sevilla", 10),
        ("塞尔塔", "Celta Vigo", 11),
        ("奥萨苏纳", "Osasuna", 12),
        ("马洛卡", "Mallorca", 13),
        ("拉斯帕尔马斯", "Las Palmas", 14),
        ("巴拉多利德", "Valladolid", 15),
        ("西班牙人", "Espanyol", 16),
        ("赫塔费", "Getafe", 17),
        ("莱加内斯", "Leganes", 18),
        ("阿拉维斯", "Alaves", 19),
        ("巴列卡诺", "Rayo Vallecano", 20),
    ],
    "serie-a": [
        ("国际米兰", "Inter Milan", 1),
        ("AC米兰", "AC Milan", 2),
        ("尤文图斯", "Juventus", 3),
        ("亚特兰大", "Atalanta", 4),
        ("博洛尼亚", "Bologna", 5),
        ("罗马", "AS Roma", 6),
        ("拉齐奥", "Lazio", 7),
        ("那不勒斯", "Napoli", 8),
        ("佛罗伦萨", "Fiorentina", 9),
        ("都灵", "Torino", 10),
        ("蒙扎", "Monza", 11),
        ("热那亚", "Genoa", 12),
        ("维罗纳", "Hellas Verona", 13),
        ("莱切", "Lecce", 14),
        ("乌迪内斯", "Udinese", 15),
        ("恩波利", "Empoli", 16),
        ("帕尔马", "Parma", 17),
        ("卡利亚里", "Cagliari", 18),
        ("威尼斯", "Venezia", 19),
        ("科莫", "Como", 20),
    ],
    "bundesliga": [
        ("拜仁慕尼黑", "Bayern Munich", 1),
        ("勒沃库森", "Bayer Leverkusen", 2),
        ("斯图加特", "V Stuttgart", 3),
        ("多特蒙德", "Borussia Dortmund", 4),
        ("莱比锡", "RB Leipzig", 5),
        ("法兰克福", "Eintracht Frankfurt", 6),
        ("沃尔夫斯堡", "Wolfsburg", 7),
        ("弗赖堡", "Freiburg", 8),
        ("霍芬海姆", "Hoffenheim", 9),
        ("柏林联合", "Union Berlin", 10),
        ("奥格斯堡", "Augsburg", 11),
        ("不来梅", "Werder Bremen", 12),
        ("美因茨", "Mainz", 13),
        ("门兴", "Borussia M'gladbach", 14),
        ("波鸿", "Bochum", 15),
        ("圣保利", "St Pauli", 16),
        ("基尔", "Holstein Kiel", 17),
        ("海登海姆", "Heidenheim", 18),
    ],
    "ligue-1": [
        ("巴黎圣日耳曼", "Paris Saint-Germain", 1),
        ("摩纳哥", "Monaco", 2),
        ("马赛", "Marseille", 3),
        ("里尔", "Lille", 4),
        ("尼斯", "Nice", 5),
        ("里昂", "Lyon", 6),
        ("朗斯", "Lens", 7),
        ("布雷斯特", "Brest", 8),
        ("雷恩", "Rennes", 9),
        ("图卢兹", "Toulouse", 10),
        ("蒙彼利埃", "Montpellier", 11),
        ("斯特拉斯堡", "Strasbourg", 12),
        ("南特", "Nantes", 13),
        ("欧塞尔", "Auxerre", 14),
        ("昂热", "Angers", 15),
        ("圣埃蒂安", "Saint-Etienne", 16),
        ("勒阿弗尔", "Le Havre", 17),
        ("兰斯", "Reims", 18),
    ],
}


def _abilities_from_rank(rank: int, total: int) -> dict:
    pct = max(0, 1 - (rank - 1) / max(total - 1, 1))
    base = 62 + pct * 28
    return {
        "attack": round(base + pct * 6),
        "defend": round(base - (1 - pct) * 4),
        "midfield": round(base),
        "speed": round(base - 2),
        "physical": round(base - 1),
    }


async def seed_league_teams(db: AsyncSession, slug: str) -> int:
    rows = LEAGUE_TEAMS.get(slug)
    if not rows:
        return 0
    comp = get_competition(slug)
    total = len(rows)
    created = updated = 0
    for cn, en, rank in rows:
        abilities = _abilities_from_rank(rank, total)
        existing = (await db.execute(
            select(Team).where(Team.competition_slug == slug, Team.name == cn)
        )).scalar_one_or_none()
        if existing:
            existing.name_en = en
            existing.rank = rank
            existing.group_name = None
            existing.flag_url = crest_url_for(cn) or existing.flag_url
            for k, v in abilities.items():
                setattr(existing, k, v)
            existing.tactic = existing.tactic or "联赛常规"
            if not existing.season:
                existing.season = season_label_for(comp)
            updated += 1
        else:
            db.add(Team(
                competition_slug=slug,
                name=cn,
                name_en=en,
                flag_url=crest_url_for(cn),
                rank=rank,
                tactic="联赛常规",
                price="-",
                group_name=None,
                season=season_label_for(comp),
                **abilities,
            ))
            created += 1
    await db.flush()
    return created + updated


async def seed_league_fixtures(db: AsyncSession, slug: str, rounds: int = 5) -> int:
    """Create upcoming league fixtures if none exist."""
    comp = get_competition(slug)
    if not comp:
        return 0

    season = season_label_for(comp)
    closing = _parse_iso(comp.get("closing_date"))
    if closing and datetime.utcnow() > closing:
        return 0

    existing = (await db.execute(
        select(func.count(Match.id)).where(Match.competition_slug == slug)
    )).scalar() or 0
    if existing > 0:
        return 0

    teams = (await db.execute(
        select(Team).where(Team.competition_slug == slug).order_by(Team.rank.asc())
    )).scalars().all()
    if len(teams) < 2:
        return 0

    names = [t.name for t in teams]
    base = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
    created = 0
    idx = 0
    for r in range(rounds):
        day = base + timedelta(days=r + 1)
        for i in range(0, len(names) - 1, 2):
            if idx >= len(names):
                break
            home, away = names[i], names[i + 1]
            if home == away:
                continue
            kickoff = day + timedelta(hours=(i // 2) * 2)
            db.add(Match(
                competition_slug=slug,
                stage="联赛",
                group_name=None,
                team_a=home,
                team_b=away,
                match_time=kickoff,
                location=comp.get("short_name", slug),
                stadium="",
                status=MATCH_UPCOMING,
                season=season,
            ))
            created += 1
        # rotate for variety
        names = names[1:] + names[:1]
    await db.flush()
    return created


async def sync_league_crests(db: AsyncSession, slug: str) -> int:
    """Backfill club crest URLs for existing league teams."""
    rows = LEAGUE_TEAMS.get(slug)
    if not rows:
        return 0
    updated = 0
    for cn, _en, _rank in rows:
        url = crest_url_for(cn)
        if not url:
            continue
        team = (await db.execute(
            select(Team).where(Team.competition_slug == slug, Team.name == cn)
        )).scalar_one_or_none()
        if team and team.flag_url != url:
            team.flag_url = url
            updated += 1
    if updated:
        await db.flush()
    return updated


async def ensure_league_data(db: AsyncSession, slug: str) -> dict:
    """Ensure club league has teams & fixtures (seed if missing)."""
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return {"status": "skip"}

    team_count = (await db.execute(
        select(func.count(Team.id)).where(Team.competition_slug == slug)
    )).scalar() or 0

    if team_count == 0:
        teams = await seed_league_teams(db, slug)
    else:
        teams = await sync_league_crests(db, slug)

    match_count = (await db.execute(
        select(func.count(Match.id)).where(Match.competition_slug == slug)
    )).scalar() or 0
    real_match_count = (await db.execute(
        select(func.count(Match.id)).where(
            Match.competition_slug == slug,
            Match.external_id.isnot(None),
        )
    )).scalar() or 0

    if match_count == 0:
        fixtures = await seed_league_fixtures(db, slug)
    elif real_match_count > 0:
        from data.match_status import cleanup_orphan_seed_matches
        await cleanup_orphan_seed_matches(db, slug)
        fixtures = 0
    else:
        fixtures = 0

    return {
        "status": "seeded" if (teams or fixtures) else "ok",
        "teams": teams,
        "fixtures": fixtures,
    }
