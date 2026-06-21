"""Background job for dashboard manual data refresh (avoids HTTP/proxy timeouts)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from db import async_session
from db.sqlite_write import IS_SQLITE, write_lock, _commit_with_retry
from crawler import run_schedule_crawler, run_team_crawler, run_all_odds_crawlers
from service.prediction_service import PredictionService
from service.write_guard import claim_heavy_job, is_heavy_job_running, release_heavy_job
from utils.logger import logger

_refresh_state: dict[str, Any] = {
    "running": False,
    "phase": None,
    "schedule": None,
    "team": None,
    "odds": None,
    "predictions": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}
_refresh_lock = asyncio.Lock()


def get_refresh_state() -> dict:
    return dict(_refresh_state)


def is_refresh_running() -> bool:
    return bool(_refresh_state.get("running"))


async def _run_crawler_phase(phase: str, fn) -> dict:
    _refresh_state["phase"] = phase
    try:
        async with async_session() as db:
            if IS_SQLITE:
                async with write_lock:
                    result = await fn(db)
                    await _commit_with_retry(db)
            else:
                result = await fn(db)
                await db.commit()
        payload = result if isinstance(result, dict) else {"status": "ok", "result": result}
        _refresh_state[phase] = payload
        return payload
    except Exception as e:
        logger.warning(f"Data refresh phase [{phase}] failed: {e}")
        payload = {"status": "failed", "error": str(e)}
        _refresh_state[phase] = payload
        return payload


async def run_data_refresh_job(predict_model: str | None = None) -> None:
    if not await claim_heavy_job("refresh"):
        logger.warning("Data refresh skipped: another heavy job is running")
        return
    async with _refresh_lock:
        if _refresh_state["running"]:
            release_heavy_job("refresh")
            return
        _refresh_state.update({
            "running": True,
            "phase": "schedule",
            "schedule": None,
            "team": None,
            "odds": None,
            "predictions": None,
            "error": None,
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
        })

    try:
        await _run_crawler_phase("schedule", run_schedule_crawler)
        await _run_crawler_phase("team", run_team_crawler)
        await _run_crawler_phase("odds", run_all_odds_crawlers)

        _refresh_state["phase"] = "predictions"
        try:
            service = PredictionService()
            async with async_session() as db:
                pred_results = await service.batch_predict(db, predict_model)
            _refresh_state["predictions"] = {"count": len(pred_results), "status": "ok"}
        except Exception as e:
            logger.warning(f"Data refresh predictions failed: {e}")
            _refresh_state["predictions"] = {"status": "failed", "error": str(e)}

        logger.info("Background data refresh finished")
    except Exception as e:
        logger.error(f"Background data refresh failed: {e}")
        _refresh_state["error"] = str(e)
    finally:
        _refresh_state["running"] = False
        _refresh_state["phase"] = "done"
        _refresh_state["finished_at"] = datetime.utcnow().isoformat()
        release_heavy_job("refresh")


async def start_data_refresh_job(predict_model: str | None = None) -> dict:
    async with _refresh_lock:
        if _refresh_state["running"] or is_heavy_job_running():
            return {"started": False, "reason": "already_running", **get_refresh_state()}
    asyncio.create_task(run_data_refresh_job(predict_model))
    return {"started": True, **get_refresh_state()}
