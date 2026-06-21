import asyncio
from datetime import datetime
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import CrawlerLog
from db.sqlite_write import IS_SQLITE, write_lock, _commit_with_retry
from utils.logger import logger

# Prevent concurrent crawlers from locking SQLite
crawler_lock = asyncio.Lock()


async def _persist_crawler_log(
    crawler_type: str,
    status: str,
    records: int = 0,
    error: str | None = None,
    start: datetime | None = None,
) -> bool:
    """Write crawler_logs in an isolated session so main crawl tx is not rolled back on lock."""
    from db import async_session

    log_entry = CrawlerLog(
        crawler_type=crawler_type,
        status=status,
        records_count=records,
        error_message=(error[:2000] if error else None),
        start_time=start or datetime.now(),
        end_time=datetime.now(),
    )
    try:
        async with async_session() as log_db:
            log_db.add(log_entry)
            if IS_SQLITE:
                async with write_lock:
                    await _commit_with_retry(log_db, retries=12)
            else:
                await log_db.commit()
        return True
    except OperationalError as exc:
        if "locked" in str(exc).lower():
            logger.warning(
                "Crawler log skipped (SQLite locked) [%s/%s]: %s",
                crawler_type, status, exc,
            )
        else:
            logger.warning("Crawler log failed [%s/%s]: %s", crawler_type, status, exc)
        return False
    except Exception as exc:
        logger.warning("Crawler log failed [%s/%s]: %s", crawler_type, status, exc)
        return False


async def _log_crawler(
    db: AsyncSession,
    crawler_type: str,
    status: str,
    records: int = 0,
    error: str | None = None,
    start: datetime | None = None,
):
    """Best-effort crawler audit log (does not use the caller session)."""
    await _persist_crawler_log(crawler_type, status, records, error, start)


async def _safe_crawler_fail(
    db: AsyncSession,
    crawler_type: str,
    exc: Exception,
    start_time: datetime,
):
    """Rollback broken transaction and attempt to write failure log."""
    logger.error(f"{crawler_type} crawler failed: {exc}")
    try:
        await db.rollback()
    except Exception:
        pass
    await _persist_crawler_log(crawler_type, "failed", 0, str(exc), start_time)
