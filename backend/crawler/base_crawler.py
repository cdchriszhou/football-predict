import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import CrawlerLog
from utils.logger import logger

# Prevent concurrent crawlers from locking SQLite
crawler_lock = asyncio.Lock()


async def _log_crawler(db: AsyncSession, crawler_type: str, status: str,
                       records: int = 0, error: str = None, start: datetime = None):
    log_entry = CrawlerLog(
        crawler_type=crawler_type,
        status=status,
        records_count=records,
        error_message=(error[:2000] if error else None),
        start_time=start or datetime.now(),
        end_time=datetime.now()
    )
    db.add(log_entry)
    await db.flush()


async def _safe_crawler_fail(db: AsyncSession, crawler_type: str, exc: Exception,
                             start_time: datetime):
    """Rollback broken transaction and attempt to write failure log."""
    logger.error(f"{crawler_type} crawler failed: {exc}")
    try:
        await db.rollback()
    except Exception:
        pass
    try:
        await _log_crawler(db, crawler_type, "failed", 0, str(exc), start_time)
    except Exception as log_err:
        logger.warning(f"Failed to write crawler log for {crawler_type}: {log_err}")
