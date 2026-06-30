from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from db import get_db
from db.models import Match
from utils.response import success, paginate
from api.auth import get_current_user
from api.competitions import resolve_competition
from api.deps import require_competition_entitlement
from data.competitions import get_competition
from data.competition_status import _parse_iso
from data.match_status import (
    include_in_today_dashboard,
    match_has_recorded_score,
    season_label_for,
    resolve_public_match_status,
    sync_match_results_throttled,
)
from data.status_constants import (
    MATCH_FINISHED,
    MATCH_UPCOMING,
    match_status_in_db_values,
    normalize_match_status,
)
from datetime import date, datetime, timedelta
from utils.datetime_helpers import china_now, beijing_day_bounds_naive, format_beijing_iso

import json
import re

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])


async def _ensure_results_synced(db: AsyncSession, comp_slug: str) -> None:
    try:
        await sync_match_results_throttled(db, comp_slug)
    except SQLAlchemyError:
        await db.rollback()
        raise


def _sort_stages(stages: list[str]) -> list[str]:
    """Sort club matchdays (第N轮) numerically; keep others lexicographic."""
    def key(s: str):
        m = re.match(r"第(\d+)轮", s or "")
        return (0, int(m.group(1))) if m else (1, s or "")

    return sorted(stages, key=key)


def _club_season_filter(comp_slug: str):
    comp = get_competition(comp_slug)
    if comp and comp.get("type") == "club":
        season = season_label_for(comp)
        if season:
            return Match.season == season
    return None


def _season_ended(comp_slug: str) -> bool:
    comp = get_competition(comp_slug)
    if not comp:
        return False
    closing = _parse_iso(comp.get("closing_date"))
    return bool(closing and datetime.utcnow() > closing)


def match_to_dict(m: Match) -> dict:
    status = resolve_public_match_status(m)
    ra, rb = m.result_a, m.result_b
    # Expose recorded scores for live and finished; hide only when not yet stored.
    if not match_has_recorded_score(m):
        ra, rb = None, None
    return {
        "id": m.id, "competition_slug": m.competition_slug,
        "stage": m.stage, "group_name": m.group_name,
        "team_a": m.team_a, "team_b": m.team_b,
        "match_time": format_beijing_iso(m.match_time),
        "location": m.location, "stadium": m.stadium,
        "result_a": ra, "result_b": rb,
        "penalty_a": m.penalty_a if match_has_recorded_score(m) else None,
        "penalty_b": m.penalty_b if match_has_recorded_score(m) else None,
        "status": status,
        "season": m.season, "matchday": m.matchday,
    }


@router.get("/list")
async def get_matches(
    competition: str = Query("worldcup-2026", description="赛事 slug"),
    stage: str = Query(None, description="阶段筛选"),
    status: str = Query(None, description="状态筛选"),
    group_name: str = Query(None, description="小组筛选 A-L"),
    date_from: str = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    comp_slug = resolve_competition(competition)
    await _ensure_results_synced(db, comp_slug)
    query = select(Match).where(Match.competition_slug == comp_slug)
    count_query = select(func.count(Match.id)).where(Match.competition_slug == comp_slug)
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        query = query.where(season_filter)
        count_query = count_query.where(season_filter)

    if stage:
        query = query.where(Match.stage == stage)
        count_query = count_query.where(Match.stage == stage)
    if status:
        status_values = match_status_in_db_values(normalize_match_status(status))
        query = query.where(Match.status.in_(status_values))
        count_query = count_query.where(Match.status.in_(status_values))
    if group_name:
        query = query.where(Match.group_name == group_name)
        count_query = count_query.where(Match.group_name == group_name)
    if date_from:
        query = query.where(Match.match_time >= datetime.strptime(date_from, "%Y-%m-%d"))
        count_query = count_query.where(Match.match_time >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.where(Match.match_time <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        count_query = count_query.where(Match.match_time <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

    total = (await db.execute(count_query)).scalar()
    matches = (await db.execute(
        query.order_by(Match.match_time.asc()).offset((page - 1) * size).limit(size)
    )).scalars().all()

    data = [match_to_dict(m) for m in matches]
    return success(paginate(data, total, page, size))


@router.get("/dates")
async def get_match_dates(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    comp_slug = resolve_competition(competition)
    date_filters = [
        Match.competition_slug == comp_slug,
        Match.match_time.isnot(None),
    ]
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        date_filters.append(season_filter)
    result = await db.execute(
        select(func.date(Match.match_time)).where(
            *date_filters,
        ).distinct().order_by(func.date(Match.match_time))
    )
    dates = [row[0] for row in result.all()]
    return success([d.isoformat() if hasattr(d, 'isoformat') else str(d) for d in dates])


@router.get("/stages")
async def get_match_stages(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Distinct stage/round labels for the current competition."""
    comp_slug = resolve_competition(competition)
    comp = get_competition(comp_slug)
    stage_filters = [
        Match.competition_slug == comp_slug,
        Match.stage.isnot(None),
        Match.stage != "",
    ]
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        stage_filters.append(season_filter)

    rows = (await db.execute(
        select(Match.stage).where(*stage_filters).distinct()
    )).scalars().all()
    stages = _sort_stages(list(rows))

    # Club leagues use matchday rounds; never expose World Cup knockout labels.
    if comp and comp.get("type") == "club":
        knockout = {"小组赛", "1/16决赛", "1/8决赛", "1/4决赛", "半决赛", "季军赛", "决赛"}
        stages = [s for s in stages if s not in knockout]

    return success(stages)


@router.get("/recent-results")
async def get_recent_results(
    competition: str = Query("worldcup-2026"),
    hours: int = Query(48, ge=1, le=168),
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Recently finished matches with scores (for dashboard)."""
    comp_slug = resolve_competition(competition)
    await _ensure_results_synced(db, comp_slug)
    cutoff = china_now().replace(tzinfo=None) - timedelta(hours=hours)
    filters = [
        Match.competition_slug == comp_slug,
        Match.match_time.isnot(None),
        Match.match_time >= cutoff,
        Match.result_a.isnot(None),
        Match.result_b.isnot(None),
    ]
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        filters.append(season_filter)
    matches = (await db.execute(
        select(Match).where(*filters).order_by(Match.match_time.desc()).limit(limit)
    )).scalars().all()
    return success([match_to_dict(m) for m in matches])


@router.get("/today")
async def get_today_matches(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    comp_slug = resolve_competition(competition)
    await _ensure_results_synced(db, comp_slug)
    today_start, today_end = beijing_day_bounds_naive()
    # Wider DB window so canonical kickoff (may differ from stale match_time) still matches today.
    query_start = today_start - timedelta(days=1)
    query_end = today_end + timedelta(days=1)
    today_filters = [
        Match.competition_slug == comp_slug,
        Match.match_time.isnot(None),
        Match.match_time >= query_start,
        Match.match_time < query_end,
    ]
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        today_filters.append(season_filter)
    matches = (await db.execute(
        select(Match).where(*today_filters).order_by(Match.match_time.asc())
    )).scalars().all()

    data = [match_to_dict(m) for m in matches if include_in_today_dashboard(m)]
    return success(data)


@router.get("/upcoming")
async def get_upcoming_matches(
    competition: str = Query("worldcup-2026"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    comp_slug = resolve_competition(competition)
    await _ensure_results_synced(db, comp_slug)
    if _season_ended(comp_slug):
        return success([])

    upcoming_filters = [
        Match.competition_slug == comp_slug,
        Match.status.in_(match_status_in_db_values(MATCH_UPCOMING)),
        Match.match_time >= china_now().replace(tzinfo=None),
    ]
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        upcoming_filters.append(season_filter)
    matches = (await db.execute(
        select(Match).where(*upcoming_filters).order_by(Match.match_time.asc()).limit(limit)
    )).scalars().all()

    data = [match_to_dict(m) for m in matches]
    return success(data)


@router.get("/{match_id}")
async def get_match_detail(match_id: int, db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_user)):
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    await _ensure_results_synced(db, match.competition_slug)
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one()

    from db.models import Team, Odds
    team_a = (await db.execute(
        select(Team).where(Team.name == match.team_a, Team.competition_slug == match.competition_slug)
    )).scalar_one_or_none()
    team_b = (await db.execute(
        select(Team).where(Team.name == match.team_b, Team.competition_slug == match.competition_slug)
    )).scalar_one_or_none()
    odds = (await db.execute(select(Odds).where(Odds.match_id == match_id))).scalar_one_or_none()

    return success({
        **match_to_dict(match),
        "team_a_detail": team_to_dict(team_a) if team_a else None,
        "team_b_detail": team_to_dict(team_b) if team_b else None,
        "odds": {
            "win_win": odds.win_win, "draw": odds.draw, "win_lose": odds.win_lose,
            "handicap": odds.handicap,
            "handicap_win": odds.handicap_win, "handicap_draw": odds.handicap_draw,
            "handicap_lose": odds.handicap_lose,
            "over_under": odds.over_under, "over_odds": odds.over_odds,
            "under_odds": odds.under_odds,
            "score_odds": json.loads(odds.score_odds) if odds.score_odds else None,
            "half_full_odds": json.loads(odds.half_full_odds) if odds.half_full_odds else None,
            "source": odds.source, "update_time": odds.update_time.isoformat() if odds.update_time else None
        } if odds else None
    })


def team_to_dict(t):
    return {
        "id": t.id, "name": t.name, "name_en": t.name_en, "flag_url": t.flag_url,
        "rank": t.rank, "attack": t.attack, "defend": t.defend,
        "midfield": t.midfield, "speed": t.speed, "physical": t.physical,
        "tactic": t.tactic, "price": t.price, "group_name": t.group_name,
        "season": t.season,
    }
