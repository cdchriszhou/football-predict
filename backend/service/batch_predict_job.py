"""In-memory state for background batch prediction jobs."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Awaitable

from sqlalchemy import select, func

from db import async_session
from db.models import Match
from data.status_constants import MATCH_UPCOMING
from service.prediction_service import PredictionService
from service.write_guard import claim_heavy_job, is_heavy_job_running, release_heavy_job
from utils.logger import logger

ProgressCb = Callable[[int, int], Awaitable[None] | None]

_batch_state: dict[str, Any] = {
    "running": False,
    "done": 0,
    "total": 0,
    "success": 0,
    "failed": 0,
    "current_match": None,
    "competition": None,
    "model": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}
_batch_lock = asyncio.Lock()


def get_batch_state() -> dict:
    return dict(_batch_state)


def is_batch_running() -> bool:
    return bool(_batch_state.get("running"))


async def run_batch_predict_job(
    model: str | None = None,
    competition_slug: str | None = "worldcup-2026",
) -> None:
    if not await claim_heavy_job("batch"):
        logger.warning("Batch predict skipped: another heavy job is running")
        return
    async with _batch_lock:
        if _batch_state["running"]:
            release_heavy_job("batch")
            return
        _batch_state.update({
            "running": True,
            "done": 0,
            "total": 0,
            "success": 0,
            "failed": 0,
            "current_match": None,
            "competition": competition_slug,
            "model": model or "auto",
            "error": None,
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
        })

    try:
        service = PredictionService()
        async with async_session() as db:
            query = select(func.count(Match.id)).where(Match.status == MATCH_UPCOMING)
            if competition_slug:
                query = query.where(Match.competition_slug == competition_slug)
            total = (await db.execute(query)).scalar() or 0
            _batch_state["total"] = total

        async def on_progress(done: int, success: int, failed: int, **extra) -> None:
            _batch_state["done"] = done
            _batch_state["success"] = success
            _batch_state["failed"] = failed
            if extra.get("current_match"):
                _batch_state["current_match"] = extra["current_match"]

        async with async_session() as db:
            await service.batch_predict(
                db,
                model,
                competition_slug=competition_slug,
                on_progress=on_progress,
            )
        logger.info(
            f"Background batch predict finished: {_batch_state['success']}/{_batch_state['total']} "
            f"(failed={_batch_state['failed']})"
        )
    except Exception as e:
        logger.error(f"Background batch predict failed: {e}")
        _batch_state["error"] = str(e)
    finally:
        _batch_state["running"] = False
        _batch_state["current_match"] = None
        _batch_state["finished_at"] = datetime.utcnow().isoformat()
        release_heavy_job("batch")


async def start_batch_predict_job(
    model: str | None = None,
    competition_slug: str | None = "worldcup-2026",
) -> dict:
    async with _batch_lock:
        if _batch_state["running"] or is_heavy_job_running():
            return {"started": False, "reason": "already_running", **get_batch_state()}
    asyncio.create_task(run_batch_predict_job(model, competition_slug))
    return {"started": True, **get_batch_state()}
