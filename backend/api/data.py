from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from api.auth import get_current_admin_user
from crawler import run_schedule_crawler, run_team_crawler, run_all_odds_crawlers
from service.prediction_service import PredictionService
from service.data_refresh_job import get_refresh_state, start_data_refresh_job
from utils.response import success, error
from utils.logger import logger

router = APIRouter()


async def _refresh_sync(db: AsyncSession, predict_model: str | None) -> dict:
    results = {}

    try:
        logger.info("Sync data refresh: schedule")
        results["schedule"] = await run_schedule_crawler(db)
    except Exception as e:
        logger.warning(f"Schedule crawler failed: {e}")
        results["schedule"] = {"status": "failed", "error": str(e)}

    try:
        results["team"] = await run_team_crawler(db)
    except Exception as e:
        logger.warning(f"Team crawler failed: {e}")
        results["team"] = {"status": "failed", "error": str(e)}

    try:
        results["odds"] = await run_all_odds_crawlers(db)
    except Exception as e:
        logger.warning(f"Odds crawler failed: {e}")
        results["odds"] = {"status": "failed", "error": str(e)}

    try:
        service = PredictionService()
        pred_results = await service.batch_predict(db, predict_model)
        results["predictions"] = {"count": len(pred_results)}
    except Exception as e:
        logger.warning(f"Batch prediction failed: {e}")
        results["predictions"] = {"status": "failed", "error": str(e)}

    return results


@router.post("/refresh")
async def refresh_data(
    background: bool = Query(True, description="后台执行，避免生产环境网关超时"),
    predict_model: str = Query("auto", description="预测模型；auto 或 rule_engine 等"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    """Refresh match, team, odds, and prediction data. Admin only."""
    actual_model = None if predict_model == "auto" else predict_model

    if background:
        state = await start_data_refresh_job(actual_model)
        if not state.get("started"):
            return error(409, "数据更新正在进行中", data=state)
        return success(state, "数据更新已在后台启动")

    logger.info(f"User {current_user} triggered sync data refresh")
    results = await _refresh_sync(db, actual_model)
    return success(results, "数据刷新完成")


@router.get("/refresh/status")
async def refresh_data_status(current_user: str = Depends(get_current_admin_user)):
    """Poll background manual refresh progress."""
    return success(get_refresh_state())
