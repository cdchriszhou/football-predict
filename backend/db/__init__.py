import os
import subprocess
import sys
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL
from db.sqlite_write import commit_session

_connect_args = {}
_engine_kwargs = {"echo": False}
if "sqlite" in DATABASE_URL:
    _connect_args = {
        "check_same_thread": False,
        "timeout": 60,
    }
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **_engine_kwargs, connect_args=_connect_args)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

if "sqlite" in DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(DeclarativeBase):
    pass


def _session_has_writes(session: AsyncSession) -> bool:
    """True when the session would need a serialized SQLite commit."""
    return bool(session.new or session.dirty or session.deleted)


async def get_db() -> AsyncSession:
    """Request-scoped session; only write paths take the global SQLite lock."""
    async with async_session() as session:
        try:
            yield session
            if _session_has_writes(session):
                await commit_session(session)
            else:
                await session.rollback()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        # Enable WAL mode for SQLite to prevent "database is locked" errors
        if "sqlite" in DATABASE_URL:
            await conn.run_sync(lambda c: c.exec_driver_sql("PRAGMA journal_mode=WAL"))
            await conn.run_sync(lambda c: c.exec_driver_sql("PRAGMA busy_timeout=60000"))
            await conn.run_sync(lambda c: c.exec_driver_sql("PRAGMA synchronous=NORMAL"))

        # Create tables for new models (safe: never drops or modifies existing tables)
        await conn.run_sync(Base.metadata.create_all)

    # Run Alembic migrations for schema upgrades (e.g. adding/removing columns).
    # Using a subprocess avoids event-loop conflicts with the async server.
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=_BACKEND_DIR,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        from utils.logger import logger
        logger.warning(f"Alembic migration note: {result.stderr.strip() or result.stdout.strip()}")


async def close_db():
    await engine.dispose()
