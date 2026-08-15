"""Seed teams for五大联赛 when live API data is unavailable.

真实赛程/阵容必须来自 football-data.org（club_data_sync）。
本模块只负责：
1. 提供 2026/27 正确参赛名单（离线兜底）
2. 刷新球队花名册
3. 清除无 external_id 的占位假赛程（不再生成假对阵）
"""

from __future__ import annotations

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from data.competitions import get_competition
from data.club_crests import crest_url_for
from data.match_status import season_label_for
from db.models import Match, Team, Player, Odds, Prediction

# slug -> list of (cn_name, en_name, rank_hint 1-based)
# Rosters aligned to 2026/27 promoted/relegated results.
LEAGUE_TEAMS: dict[str, list[tuple[str, str, int]]] = {
    "premier-league": [
        ("阿森纳", "Arsenal", 1),
        ("曼城", "Manchester City", 2),
        ("利物浦", "Liverpool", 3),
        ("切尔西", "Chelsea", 4),
        ("纽卡斯尔联", "Newcastle United", 5),
        ("阿斯顿维拉", "Aston Villa", 6),
        ("曼联", "Manchester United", 7),
        ("热刺", "Tottenham Hotspur", 8),
        ("布莱顿", "Brighton", 9),
        ("水晶宫", "Crystal Palace", 10),
        ("富勒姆", "Fulham", 11),
        ("布伦特福德", "Brentford", 12),
        ("伯恩茅斯", "AFC Bournemouth", 13),
        ("埃弗顿", "Everton", 14),
        ("诺丁汉森林", "Nottingham Forest", 15),
        ("利兹联", "Leeds United", 16),
        ("桑德兰", "Sunderland", 17),
        ("伊普斯维奇", "Ipswich Town", 18),
        ("考文垂", "Coventry City", 19),
        ("赫尔城", "Hull City", 20),
    ],
    "la-liga": [
        ("巴萨", "Barcelona", 1),
        ("皇马", "Real Madrid", 2),
        ("马竞", "Atletico Madrid", 3),
        ("毕尔巴鄂", "Athletic Bilbao", 4),
        ("比利亚雷亚尔", "Villarreal", 5),
        ("贝蒂斯", "Real Betis", 6),
        ("皇家社会", "Real Sociedad", 7),
        ("塞维利亚", "Sevilla", 8),
        ("瓦伦西亚", "Valencia", 9),
        ("塞尔塔", "Celta Vigo", 10),
        ("奥萨苏纳", "Osasuna", 11),
        ("巴列卡诺", "Rayo Vallecano", 12),
        ("西班牙人", "Espanyol", 13),
        ("赫塔费", "Getafe", 14),
        ("阿拉维斯", "Alaves", 15),
        ("埃尔切", "Elche", 16),
        ("莱万特", "Levante", 17),
        ("桑坦德竞技", "Racing Santander", 18),
        ("拉科鲁尼亚", "Deportivo La Coruna", 19),
        ("马拉加", "Malaga", 20),
    ],
    "serie-a": [
        ("国际米兰", "Inter Milan", 1),
        ("那不勒斯", "Napoli", 2),
        ("尤文图斯", "Juventus", 3),
        ("AC米兰", "AC Milan", 4),
        ("亚特兰大", "Atalanta", 5),
        ("罗马", "AS Roma", 6),
        ("拉齐奥", "Lazio", 7),
        ("佛罗伦萨", "Fiorentina", 8),
        ("博洛尼亚", "Bologna", 9),
        ("都灵", "Torino", 10),
        ("乌迪内斯", "Udinese", 11),
        ("热那亚", "Genoa", 12),
        ("科莫", "Como", 13),
        ("帕尔马", "Parma", 14),
        ("卡利亚里", "Cagliari", 15),
        ("莱切", "Lecce", 16),
        ("萨索洛", "Sassuolo", 17),
        ("威尼斯", "Venezia", 18),
        ("弗罗西诺内", "Frosinone", 19),
        ("蒙扎", "Monza", 20),
    ],
    "bundesliga": [
        ("拜仁慕尼黑", "Bayern Munich", 1),
        ("勒沃库森", "Bayer Leverkusen", 2),
        ("多特蒙德", "Borussia Dortmund", 3),
        ("莱比锡", "RB Leipzig", 4),
        ("法兰克福", "Eintracht Frankfurt", 5),
        ("斯图加特", "VfB Stuttgart", 6),
        ("弗赖堡", "Freiburg", 7),
        ("不来梅", "Werder Bremen", 8),
        ("门兴", "Borussia M'gladbach", 9),
        ("柏林联合", "Union Berlin", 10),
        ("霍芬海姆", "Hoffenheim", 11),
        ("奥格斯堡", "Augsburg", 12),
        ("美因茨", "Mainz", 13),
        ("汉堡", "Hamburger SV", 14),
        ("科隆", "FC Koln", 15),
        ("沙尔克04", "Schalke 04", 16),
        ("帕德博恩", "SC Paderborn", 17),
        ("埃尔弗斯贝格", "SV Elversberg", 18),
    ],
    "ligue-1": [
        ("巴黎圣日耳曼", "Paris Saint-Germain", 1),
        ("摩纳哥", "Monaco", 2),
        ("马赛", "Marseille", 3),
        ("里尔", "Lille", 4),
        ("里昂", "Lyon", 5),
        ("尼斯", "Nice", 6),
        ("朗斯", "Lens", 7),
        ("雷恩", "Rennes", 8),
        ("斯特拉斯堡", "Strasbourg", 9),
        ("布雷斯特", "Brest", 10),
        ("图卢兹", "Toulouse", 11),
        ("洛里昂", "Lorient", 12),
        ("欧塞尔", "Auxerre", 13),
        ("昂热", "Angers", 14),
        ("勒阿弗尔", "Le Havre", 15),
        ("巴黎FC", "Paris FC", 16),
        ("特鲁瓦", "Troyes", 17),
        ("勒芒", "Le Mans", 18),
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


async def purge_seed_fixtures(db: AsyncSession, slug: str) -> int:
    """Delete placeholder fixtures that were never linked to an external API id."""
    orphan_ids = list((await db.execute(
        select(Match.id).where(
            Match.competition_slug == slug,
            Match.external_id.is_(None),
        )
    )).scalars().all())
    if not orphan_ids:
        return 0
    await db.execute(delete(Prediction).where(Prediction.match_id.in_(orphan_ids)))
    await db.execute(delete(Odds).where(Odds.match_id.in_(orphan_ids)))
    result = await db.execute(delete(Match).where(Match.id.in_(orphan_ids)))
    await db.flush()
    return int(result.rowcount or 0)


async def seed_league_teams(db: AsyncSession, slug: str, *, replace: bool = True) -> dict:
    """Upsert 2026/27 roster; optionally remove teams no longer in the league."""
    rows = LEAGUE_TEAMS.get(slug)
    if not rows:
        return {"upserted": 0, "removed": 0}
    comp = get_competition(slug)
    total = len(rows)
    season = season_label_for(comp)
    wanted = {cn for cn, _en, _rank in rows}
    upserted = 0

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
            existing.season = season
            for k, v in abilities.items():
                setattr(existing, k, v)
            existing.tactic = existing.tactic or "联赛常规"
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
                season=season,
                **abilities,
            ))
        upserted += 1

    removed = 0
    if replace:
        obsolete = (await db.execute(
            select(Team).where(
                Team.competition_slug == slug,
                Team.name.not_in(wanted),
            )
        )).scalars().all()
        for team in obsolete:
            await db.execute(delete(Player).where(Player.team_id == team.id))
            await db.delete(team)
            removed += 1

    await db.flush()
    return {"upserted": upserted, "removed": removed}


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
    """Ensure club league roster is correct; purge fake fixtures; never invent matches."""
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return {"status": "skip"}

    roster = await seed_league_teams(db, slug, replace=True)
    purged = await purge_seed_fixtures(db, slug)

    match_count = (await db.execute(
        select(func.count(Match.id)).where(Match.competition_slug == slug)
    )).scalar() or 0
    real_match_count = (await db.execute(
        select(func.count(Match.id)).where(
            Match.competition_slug == slug,
            Match.external_id.isnot(None),
        )
    )).scalar() or 0

    return {
        "status": "seeded",
        "teams": roster.get("upserted", 0),
        "teams_removed": roster.get("removed", 0),
        "fixtures": 0,
        "fixtures_purged": purged,
        "match_count": match_count,
        "real_match_count": real_match_count,
        "note": "fixtures require football-data.org sync" if real_match_count == 0 else "ok",
    }
