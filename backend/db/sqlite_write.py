"""Serialize SQLite writes and retry commits when the DB is briefly locked."""
from __future__ import annotations

import asyncio

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from config import DATABASE_URL
from utils.logger import logger

IS_SQLITE = "sqlite" in (DATABASE_URL or "")


class _ReentrantAsyncLock:
    """asyncio.Lock that can be acquired multiple times by the same task (nested get_db + sync)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._depth = 0
        self._owner: asyncio.Task | None = None

    async def __aenter__(self):
        task = asyncio.current_task()
        if self._owner is task:
            self._depth += 1
            return self
        await self._lock.acquire()
        self._owner = task
        self._depth = 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._depth > 1:
            self._depth -= 1
            return False
        self._owner = None
        self._depth = 0
        self._lock.release()
        return False


write_lock = _ReentrantAsyncLock()


async def commit_session(db: AsyncSession, *, retries: int = 8) -> None:
    """Commit with optional global lock and exponential backoff (SQLite only)."""
    if not IS_SQLITE:
        await db.commit()
        return

    async with write_lock:
        await _commit_with_retry(db, retries=retries)


async def _commit_with_retry(db: AsyncSession, *, retries: int = 8) -> None:
    for attempt in range(retries):
        try:
            await db.commit()
            return
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= retries - 1:
                raise
            wait = 0.25 * (attempt + 1)
            logger.warning(
                f"SQLite locked on commit, retry {attempt + 1}/{retries} in {wait:.1f}s"
            )
            await db.rollback()
            await asyncio.sleep(wait)


async def flush_session(db: AsyncSession, *, retries: int = 8) -> None:
    """Flush pending changes with retry when SQLite is briefly locked."""
    if not IS_SQLITE:
        await db.flush()
        return

    async with write_lock:
        for attempt in range(retries):
            try:
                await db.flush()
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= retries - 1:
                    raise
                wait = 0.25 * (attempt + 1)
                logger.warning(
                    f"SQLite locked on flush, retry {attempt + 1}/{retries} in {wait:.1f}s"
                )
                await asyncio.sleep(wait)


async def run_db_write(db: AsyncSession, write_fn, *, retries: int = 8) -> None:
    """Run a write callback under the global SQLite lock (no-op lock on other DBs)."""
    if not IS_SQLITE:
        await write_fn()
        await db.commit()
        return

    async with write_lock:
        for attempt in range(retries):
            try:
                await write_fn()
                await db.commit()
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= retries - 1:
                    raise
                wait = 0.25 * (attempt + 1)
                logger.warning(
                    f"SQLite locked on write, retry {attempt + 1}/{retries} in {wait:.1f}s"
                )
                await db.rollback()
                await asyncio.sleep(wait)
