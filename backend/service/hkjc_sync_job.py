"""Background HKJC sync so HTTP handlers return immediately (avoids blocking the whole API)."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from data.hkjc_data import HKJC_DATA_SOURCE
from db import async_session
from db.sqlite_write import commit_session
from service.hkjc_backtest import compute_backtest
from service.hkjc_sync import (
    sync_active_meetings,
    sync_meetings_from_stored_results,
    sync_race_results,
)
from utils.logger import logger


@dataclass
class HkjcSyncJobState:
    running: bool = False
    phase: str = ""
    progress: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    result: dict | None = None


_state = HkjcSyncJobState()
_task: asyncio.Task | None = None


def sync_status_payload() -> dict:
    return asdict(_state)


def is_sync_running() -> bool:
    return _state.running


async def _execute_sync(sync_results: bool, result_days: int) -> None:
    global _state
    _state.running = True
    _state.error = None
    _state.result = None
    _state.started_at = datetime.utcnow().isoformat()
    _state.finished_at = None
    _state.phase = "meetings"
    _state.progress = "正在同步赛事日与排位…"

    try:
        async with async_session() as db:
            meetings = await sync_active_meetings(db, force=True, commit=True)
            results_count = 0
            if sync_results:
                _state.phase = "results"
                _state.progress = f"正在同步近 {result_days} 天赛果…"
                results_count = await sync_race_results(db, days=result_days, commit=True)
            _state.phase = "finalize"
            _state.progress = "正在整理赛事日状态…"
            await sync_meetings_from_stored_results(db, commit=True)
            _state.phase = "backtest"
            _state.progress = "正在计算回测…"
            try:
                backtest = await compute_backtest(db)
            except Exception as exc:
                logger.warning(f"HKJC backtest after sync failed: {exc}")
                backtest = {
                    "period": "回测暂不可用",
                    "races_evaluated": 0,
                    "win_hit_rate": 0.0,
                    "place_top3_rate": 0.0,
                    "high_confidence_hit": 0.0,
                    "model_version": "hkjc-live-v1",
                    "last_retrain": None,
                    "data_source": HKJC_DATA_SOURCE,
                    "notes": ["赛果已同步，回测计算出现异常，请稍后刷新回测页"],
                }
            await commit_session(db)
            _state.result = {
                "meetings_synced": len(meetings),
                "results_synced": results_count,
                "backtest": backtest,
                "data_source": HKJC_DATA_SOURCE,
            }
    except OperationalError as exc:
        if "locked" in str(exc).lower():
            _state.error = "数据库繁忙，请稍后重试（可能另有写入任务正在进行）"
        else:
            _state.error = f"数据库错误: {exc}"
        logger.exception("HKJC background sync failed (db)")
    except Exception as exc:
        _state.error = f"同步失败: {exc}"
        logger.exception("HKJC background sync failed")
    finally:
        _state.running = False
        _state.finished_at = datetime.utcnow().isoformat()
        if not _state.error:
            _state.progress = "同步完成"
        global _task
        _task = None


def start_background_sync(*, sync_results: bool = True, result_days: int = 14) -> bool:
    """Schedule sync on the event loop. Returns False if already running."""
    global _task
    if _state.running:
        return False
    _task = asyncio.create_task(_execute_sync(sync_results, result_days))
    return True


async def run_sync_inline(
    db: AsyncSession,
    *,
    sync_results: bool = True,
    result_days: int = 14,
) -> dict:
    """Synchronous path for scripts/tests (uses caller's session)."""
    meetings = await sync_active_meetings(db, force=True, commit=True)
    results_count = 0
    if sync_results:
        results_count = await sync_race_results(db, days=result_days, commit=True)
    await sync_meetings_from_stored_results(db, commit=True)
    backtest = await compute_backtest(db)
    return {
        "meetings_synced": len(meetings),
        "results_synced": results_count,
        "backtest": backtest,
        "data_source": HKJC_DATA_SOURCE,
    }
