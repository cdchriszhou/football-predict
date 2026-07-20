import time

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, get_db_user, verify_token
from data.competitions import get_competition, list_competitions, is_valid_competition
from data.competition_status import compute_season_status
from data.match_status import maintain_competition_matches, season_label_for
from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING
from data.league_seed import ensure_league_data
from db import get_db
from db.models import Match, Team
from service.user_access import check_competition_access
from utils.response import success
from utils.logger import logger

router = APIRouter()
_security = HTTPBearer()

# Avoid running heavy match maintenance on every competitions list poll.
_MAINTAIN_LIST_INTERVAL_SEC = 300
_last_maintain_all_at: float = 0


async def _stats_by_slug(db: AsyncSession) -> tuple[dict, dict]:
    """Aggregate match/team counts per competition in two lightweight queries."""
    match_rows = (await db.execute(
        select(
            Match.competition_slug,
            Match.season,
            func.count(Match.id).label("matches"),
            func.sum(case((Match.status == MATCH_UPCOMING, 1), else_=0)).label("upcoming"),
            func.sum(case((Match.status == MATCH_LIVE, 1), else_=0)).label("live"),
            func.sum(case((Match.status == MATCH_FINISHED, 1), else_=0)).label("finished"),
        ).group_by(Match.competition_slug, Match.season)
    )).all()
    team_rows = (await db.execute(
        select(
            Team.competition_slug,
            func.count(Team.id).label("teams"),
        ).group_by(Team.competition_slug)
    )).all()

    match_stats: dict[str, dict] = {}
    for r in match_rows:
        slug = r.competition_slug
        comp = get_competition(slug)
        if comp and comp.get("type") == "club":
            expected = season_label_for(comp)
            if expected and r.season != expected:
                continue
        bucket = match_stats.setdefault(slug, {
            "matches": 0, "upcoming": 0, "live": 0, "finished": 0,
        })
        bucket["matches"] += int(r.matches or 0)
        bucket["upcoming"] += int(r.upcoming or 0)
        bucket["live"] += int(r.live or 0)
        bucket["finished"] += int(r.finished or 0)

    team_stats = {r.competition_slug: int(r.teams or 0) for r in team_rows}
    return match_stats, team_stats


async def _ensure_league_data_if_empty(db: AsyncSession) -> None:
    """Seed club leagues when DB has no rows yet (first visit / fresh install)."""
    total = (await db.execute(select(func.count(Match.id)))).scalar() or 0
    if total > 0:
        return
    for comp in list_competitions():
        if comp.get("type") == "club":
            try:
                await ensure_league_data(db, comp["slug"])
            except Exception:
                pass
    await db.flush()


async def _maintain_all_competitions_throttled(db: AsyncSession) -> None:
    """Run match maintenance at most once per interval."""
    global _last_maintain_all_at
    now = time.monotonic()
    if now - _last_maintain_all_at < _MAINTAIN_LIST_INTERVAL_SEC:
        return
    _last_maintain_all_at = now
    for comp in list_competitions():
        try:
            await maintain_competition_matches(db, comp["slug"])
        except Exception as e:
            logger.warning(f"Match maintenance failed for {comp['slug']}: {e}")


@router.get("")
async def get_competitions(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """List all supported competitions with cached DB stats (fast path, no sync on read)."""
    response.headers["Cache-Control"] = "no-store"
    match_stats, team_stats = {}, {}
    try:
        match_stats, team_stats = await _stats_by_slug(db)
    except Exception as e:
        logger.warning(f"Competition stats query failed: {e}")
        await db.rollback()

    items = []
    for comp in list_competitions():
        slug = comp["slug"]
        ms = match_stats.get(slug, {})
        stats = {
            "matches": ms.get("matches", 0),
            "teams": team_stats.get(slug, 0),
            "upcoming": ms.get("upcoming", 0),
            "live": ms.get("live", 0),
            "finished": ms.get("finished", 0),
        }
        items.append({
            "slug": slug,
            "name_key": comp["name_key"],
            "short_name": comp["short_name"],
            "type": comp["type"],
            "theme_color": comp["theme_color"],
            "features": comp["features"],
            "opening_date": comp.get("opening_date"),
            "closing_date": comp.get("closing_date"),
            "timezone": comp.get("timezone"),
            "timezone_label_key": comp.get("timezone_label_key"),
            "season_status": compute_season_status(comp, stats),
            "stats": stats,
        })
    return success(items)


@router.get("/{slug}")
async def get_competition_detail(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    comp = get_competition(slug)
    if not comp:
        raise HTTPException(status_code=404, detail="赛事不存在")

    user = await get_db_user(db, username=current_user)
    payload = verify_token(credentials.credentials)
    is_admin = bool(payload.get("adm")) or (user and user.is_admin)
    ok, msg = check_competition_access(user, slug, is_admin=is_admin)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)

    # Match maintenance runs on a schedule; do not block page reads (SQLite lock / proxy timeout).
    season = season_label_for(comp)
    match_filters = [Match.competition_slug == slug]
    if comp.get("type") == "club" and season:
        match_filters.append(Match.season == season)

    match_count = (await db.execute(
        select(func.count(Match.id)).where(*match_filters)
    )).scalar() or 0
    team_count = (await db.execute(
        select(func.count(Team.id)).where(Team.competition_slug == slug)
    )).scalar() or 0
    upcoming = (await db.execute(
        select(func.count(Match.id)).where(
            *match_filters,
            Match.status == MATCH_UPCOMING,
        )
    )).scalar() or 0
    live = (await db.execute(
        select(func.count(Match.id)).where(
            *match_filters,
            Match.status == MATCH_LIVE,
        )
    )).scalar() or 0
    finished = (await db.execute(
        select(func.count(Match.id)).where(
            *match_filters,
            Match.status == MATCH_FINISHED,
        )
    )).scalar() or 0

    stats = {
        "matches": match_count,
        "teams": team_count,
        "upcoming": upcoming,
        "live": live,
        "finished": finished,
    }

    return success({
        **{k: comp.get(k) for k in (
            "slug", "name_key", "short_name", "type", "theme_color", "features",
            "opening_date", "closing_date", "season_year",
            "timezone", "timezone_label_key",
        )},
        "season_status": compute_season_status(comp, stats),
        "stats": stats,
    })


def resolve_competition(competition: str | None) -> str:
    slug = competition or "worldcup-2026"
    if not is_valid_competition(slug):
        raise HTTPException(status_code=400, detail=f"未知赛事: {slug}")
    return slug
