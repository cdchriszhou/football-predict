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
    confirmed_scores_from_history,
    include_in_today_dashboard,
    match_has_recorded_score,
    season_label_for,
    resolve_public_match_status,
    sync_match_results_for_read,
)
from data.status_constants import (
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_UPCOMING,
    match_status_in_db_values,
    normalize_match_status,
)
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from utils.datetime_helpers import china_now, beijing_day_bounds_naive, format_beijing_iso

import json
import re

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])


async def _ensure_results_synced(db: AsyncSession, comp_slug: str) -> None:
    """Best-effort score sync; never block the response on maintenance work."""
    try:
        await sync_match_results_for_read(db, comp_slug)
    except SQLAlchemyError:
        await db.rollback()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass


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


def _as_match_row(m: Match | dict) -> Match | SimpleNamespace:
    if isinstance(m, dict):
        return SimpleNamespace(**m)
    return m


def match_to_dict(m: Match, *, knockout_by_no: dict | None = None) -> dict:
    m = _as_match_row(m)
    status = resolve_public_match_status(m)
    ra, rb = m.result_a, m.result_b
    pa, pb = m.penalty_a, m.penalty_b
    if not match_has_recorded_score(m):
        hist = confirmed_scores_from_history(m)
        if hist:
            ra, rb = hist["result_a"], hist["result_b"]
            pa, pb = hist.get("penalty_a"), hist.get("penalty_b")
            if status != MATCH_LIVE:
                status = MATCH_FINISHED
    # Expose recorded scores for live and finished; hide only when not yet stored.
    if ra is None or rb is None:
        ra, rb = None, None
        pa, pb = None, None

    from data.match_status import history_match_overlay
    meta = history_match_overlay(m)
    if meta.get("penalty_a") is not None and meta.get("penalty_b") is not None:
        pa, pb = meta["penalty_a"], meta["penalty_b"]
    extra_time = bool(meta.get("extra_time"))
    regulation_a = meta.get("regulation_a")
    regulation_b = meta.get("regulation_b")

    team_a, team_b = m.team_a, m.team_b
    if knockout_by_no is not None and m.competition_slug == "worldcup-2026":
        from data.knockout_advance import display_teams_for_match
        team_a, team_b = display_teams_for_match(m, knockout_by_no)

    return {
        "id": m.id, "competition_slug": m.competition_slug,
        "stage": m.stage, "group_name": m.group_name,
        "team_a": team_a, "team_b": team_b,
        "match_time": format_beijing_iso(m.match_time),
        "location": m.location, "stadium": m.stadium,
        "result_a": ra, "result_b": rb,
        "penalty_a": pa,
        "penalty_b": pb,
        "extra_time": extra_time,
        "regulation_a": regulation_a,
        "regulation_b": regulation_b,
        "status": status,
        "season": m.season, "matchday": m.matchday,
    }


async def _knockout_by_no(db: AsyncSession, comp_slug: str) -> dict | None:
    if comp_slug != "worldcup-2026":
        return None
    from data.knockout_advance import load_knockout_slot_index_cached
    return await load_knockout_slot_index_cached(db, comp_slug)


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

    ko_index = await _knockout_by_no(db, comp_slug)
    data = [match_to_dict(m, knockout_by_no=ko_index) for m in matches]
    return success(paginate(data, total, page, size))


@router.get("/knockout-bracket")
async def get_knockout_bracket(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """All knockout stages in one response for the bracket view."""
    comp_slug = resolve_competition(competition)
    await _ensure_results_synced(db, comp_slug)
    if comp_slug == "worldcup-2026":
        from data.knockout_advance import (
            ensure_knockout_fixtures,
            advance_knockout_teams,
            invalidate_knockout_slot_index_cache,
        )

        created = await ensure_knockout_fixtures(db, comp_slug)
        try:
            from service.write_guard import is_heavy_job_running
            if created or not is_heavy_job_running():
                await advance_knockout_teams(db, comp_slug, flush=False)
        except Exception:
            pass
        invalidate_knockout_slot_index_cache(comp_slug)

    ko_index = await _knockout_by_no(db, comp_slug)
    stages = ["1/16决赛", "1/8决赛", "1/4决赛", "半决赛", "季军赛", "决赛"]
    payload: dict[str, list] = {}
    for stage in stages:
        rows = list((await db.execute(
            select(Match).where(
                Match.competition_slug == comp_slug,
                Match.stage == stage,
            ).order_by(Match.match_time.asc())
        )).scalars().all())
        payload[stage] = [match_to_dict(m, knockout_by_no=ko_index) for m in rows]

    slots: dict[str, dict] = {}
    if ko_index:
        for match_no, row in ko_index.items():
            if row is None:
                continue
            slots[str(match_no)] = match_to_dict(row, knockout_by_no=ko_index)
    payload["slots"] = slots
    return success(payload)


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


async def _ensure_knockout_display_ready(db: AsyncSession, comp_slug: str) -> None:
    """Advance feeder placeholders so dashboard/recent APIs show real team names."""
    if comp_slug != "worldcup-2026":
        return
    try:
        from data.knockout_advance import advance_knockout_teams, invalidate_knockout_slot_index_cache
        from service.write_guard import is_heavy_job_running

        if not is_heavy_job_running():
            updated = await advance_knockout_teams(db, comp_slug, flush=True)
            if updated:
                invalidate_knockout_slot_index_cache(comp_slug)
    except Exception:
        pass


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
    await _ensure_knockout_display_ready(db, comp_slug)
    cutoff = china_now().replace(tzinfo=None) - timedelta(hours=hours)
    filters = [
        Match.competition_slug == comp_slug,
        Match.match_time.isnot(None),
        Match.match_time >= cutoff,
    ]
    season_filter = _club_season_filter(comp_slug)
    if season_filter is not None:
        filters.append(season_filter)
    matches = (await db.execute(
        select(Match).where(*filters).order_by(Match.match_time.desc()).limit(limit * 4)
    )).scalars().all()
    ko_index = await _knockout_by_no(db, comp_slug)
    data: list[dict] = []
    for m in matches:
        row = match_to_dict(m, knockout_by_no=ko_index)
        if row.get("result_a") is not None and row.get("result_b") is not None:
            data.append(row)
        if len(data) >= limit:
            break
    return success(data)


@router.get("/today")
async def get_today_matches(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    comp_slug = resolve_competition(competition)
    await _ensure_results_synced(db, comp_slug)
    await _ensure_knockout_display_ready(db, comp_slug)
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

    kickoff_today = [m for m in matches if include_in_today_dashboard(m)]
    source = kickoff_today
    # Rest day: 今日赛果 still shows yesterday's finished fixtures (World Cup).
    if comp_slug == "worldcup-2026" and not kickoff_today:
        recent_cutoff = today_start - timedelta(days=1)
        source = list((await db.execute(
            select(Match).where(
                Match.competition_slug == comp_slug,
                Match.match_time.isnot(None),
                Match.match_time >= recent_cutoff,
                Match.match_time < today_start,
            ).order_by(Match.match_time.asc())
        )).scalars().all())

    ko_index = await _knockout_by_no(db, comp_slug)
    data = [match_to_dict(m, knockout_by_no=ko_index) for m in source]
    if comp_slug == "worldcup-2026" and not kickoff_today:
        data = [
            d for d in data
            if d.get("result_a") is not None and d.get("result_b") is not None
        ]
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

    ko_index = await _knockout_by_no(db, comp_slug)
    data = [match_to_dict(m, knockout_by_no=ko_index) for m in matches]
    return success(data)


@router.get("/{match_id}")
async def get_match_detail(match_id: int, db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_user)):
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    await _ensure_results_synced(db, match.competition_slug)
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one()

    from db.models import Team, Odds
    ko_index = await _knockout_by_no(db, match.competition_slug)
    payload = match_to_dict(match, knockout_by_no=ko_index)
    names_a = [n for n in {payload.get("team_a"), match.team_a} if n]
    names_b = [n for n in {payload.get("team_b"), match.team_b} if n]
    team_a = None
    team_b = None
    if names_a:
        team_a = (await db.execute(
            select(Team).where(
                Team.competition_slug == match.competition_slug,
                Team.name.in_(names_a),
            )
        )).scalar_one_or_none()
    if names_b:
        team_b = (await db.execute(
            select(Team).where(
                Team.competition_slug == match.competition_slug,
                Team.name.in_(names_b),
            )
        )).scalar_one_or_none()
    odds = (await db.execute(select(Odds).where(Odds.match_id == match_id))).scalar_one_or_none()

    return success({
        **payload,
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
