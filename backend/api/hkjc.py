from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_user
from api.deps import require_competition_entitlement
from data.hkjc_data import HKJC_DATA_SOURCE, HKJC_DISCLAIMER
from db import get_db
from service.hkjc_backtest import compute_backtest
from service.hkjc_engine import (
    analyze_meeting_picks,
    analyze_race_async,
    build_purchase_advice,
    is_race_finished,
)
from service.hkjc_sync import (
    build_meeting_winners,
    build_schedule_context,
    get_meeting,
    get_race,
    list_horses,
    list_meetings,
    list_races_for_meeting,
)
from service.hkjc_sync_job import (
    is_sync_running,
    start_background_sync,
    sync_status_payload,
)
from sqlalchemy.ext.asyncio import AsyncSession
from utils.response import success
from utils.logger import logger

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])


@router.get("/dashboard")
async def hkjc_dashboard(
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    meetings = await list_meetings(db, refresh=refresh)
    featured = next((m for m in meetings if m.get("featured")), meetings[0] if meetings else None)
    featured_detail = None
    meeting_picks = []
    meeting_winners = []
    if featured:
        featured_detail = await get_meeting(db, featured["id"], refresh=refresh)
        races = await list_races_for_meeting(db, featured["id"])
        meeting_picks = analyze_meeting_picks(featured["id"], races)
        if featured_detail:
            meeting_winners = await build_meeting_winners(db, featured_detail, races)

    backtest = await compute_backtest(db)
    horses = await list_horses(db)
    schedule = build_schedule_context(meetings, featured_detail)

    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        "stats": {
            "meetings": len(meetings),
            "total_races": sum(m.get("race_count", 0) for m in meetings),
            "horses": len(horses),
            "model_hit_rate": backtest.get("win_hit_rate"),
            "place_top3_rate": backtest.get("place_top3_rate"),
        },
        "schedule": schedule,
        "featured_meeting": featured_detail,
        "meeting_picks": meeting_picks,
        "meeting_winners": meeting_winners,
        "backtest": backtest,
        "last_synced_at": featured.get("synced_at") if featured else None,
    })


@router.get("/purchase-advice")
async def hkjc_purchase_advice(
    refresh: bool = Query(False),
    limit: int = Query(12, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """All race meetings with per-race horse purchase recommendations."""
    meetings = await list_meetings(db, refresh=refresh)
    meetings = meetings[:limit]
    races_by_meeting: dict[str, list] = {}
    last_synced = None
    for m in meetings:
        races_by_meeting[m["id"]] = await list_races_for_meeting(db, m["id"])
        if m.get("synced_at") and (last_synced is None or m["synced_at"] > last_synced):
            last_synced = m["synced_at"]
    advice_meetings = build_purchase_advice(meetings, races_by_meeting)
    preview_races = sum(
        len([r for r in m["races"] if r["display_mode"] == "preview"])
        for m in advice_meetings
    )
    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        "updated_at": last_synced,
        "preview_race_count": preview_races,
        "meetings": advice_meetings,
    })


@router.get("/meetings")
async def hkjc_meetings(
    refresh: bool = Query(False),
    past_days: int = Query(7, ge=1, le=30),
    future_days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    meetings = await list_meetings(
        db,
        refresh=refresh,
        past_days=past_days,
        future_days=future_days,
    )
    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        "meetings": meetings,
        "window": {"past_days": past_days, "future_days": future_days},
    })


@router.get("/meetings/{meeting_id}")
async def hkjc_meeting_detail(
    meeting_id: str,
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    meeting = await get_meeting(db, meeting_id, refresh=refresh)
    if not meeting:
        raise HTTPException(status_code=404, detail="暂无该赛事日数据，请稍后刷新或同步")
    races = await list_races_for_meeting(db, meeting_id)
    picks = analyze_meeting_picks(meeting_id, races)
    all_finished = bool(races) and all(is_race_finished(r) for r in races)
    display_mode = "results" if meeting.get("status") == "RESULTS" or all_finished else "preview"
    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        "display_mode": display_mode,
        **meeting,
        "race_picks": picks,
    })


@router.get("/races/{race_id}")
async def hkjc_race_detail(
    race_id: str,
    refresh: bool = Query(False),
    use_ai: bool = Query(True, description="融合大模型排序（需已配置 API Key）"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    race = await get_race(db, race_id, refresh=refresh)
    if not race:
        raise HTTPException(status_code=404, detail="场次不存在或尚未同步排位数据")
    meeting = await get_meeting(db, race["meeting_id"])
    analysis = await analyze_race_async(race, use_ai=use_ai)
    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        "meeting": meeting,
        "race": {
            "id": race["id"],
            "meeting_id": race["meeting_id"],
            "race_no": race["race_no"],
            "name": race["name"],
            "distance_m": race["distance_m"],
            "distance_category": race["distance_category"],
            "class": race["class"],
            "track_type": race["track_type"],
            "start_time": race["start_time"],
            "prize_hkd": race.get("prize_hkd"),
            "risk_level": race["risk_level"],
            "is_finished": is_race_finished(race),
        },
        "analysis": analysis,
    })


@router.get("/horses")
async def hkjc_horses(
    refresh: bool = Query(False, description="从官网排位表补全马龄/性别/评分"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    horses = await list_horses(db, refresh_profiles=refresh, ensure=True)
    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        "horses": horses,
    })


@router.get("/backtest")
async def hkjc_backtest(
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    data = await compute_backtest(db)
    return success({
        "disclaimer": HKJC_DISCLAIMER,
        "data_source": HKJC_DATA_SOURCE,
        **data,
    })


@router.get("/sync/status")
async def hkjc_sync_status(
    current_user: str = Depends(get_current_user),
):
    """Poll background HKJC sync progress."""
    return success(sync_status_payload())


@router.post("/sync")
async def hkjc_sync(
    sync_results: bool = Query(True),
    result_days: int = Query(14, ge=7, le=90),
    current_user: str = Depends(get_current_user),
):
    """Start HKJC sync in background; use GET /sync/status to poll."""
    if is_sync_running():
        return success({
            "status": "running",
            "message": "同步任务进行中，请稍候",
            **sync_status_payload(),
        })
    started = start_background_sync(sync_results=sync_results, result_days=result_days)
    if not started:
        raise HTTPException(status_code=409, detail="无法启动同步任务")
    return success({
        "status": "started",
        "message": "同步已开始，可在后台继续浏览其他页面",
        **sync_status_payload(),
    })
