"""Prevent overlapping heavy SQLite write jobs (refresh vs batch predict)."""
from __future__ import annotations

import asyncio
from typing import Literal

JobName = Literal["refresh", "batch"]

_active_job: JobName | None = None
_guard_lock = asyncio.Lock()


def is_heavy_job_running() -> bool:
    return _active_job is not None


def get_active_heavy_job() -> JobName | None:
    return _active_job


async def claim_heavy_job(name: JobName) -> bool:
    global _active_job
    async with _guard_lock:
        if _active_job is not None:
            return False
        _active_job = name
        return True


def release_heavy_job(name: JobName) -> None:
    global _active_job
    if _active_job == name:
        _active_job = None
