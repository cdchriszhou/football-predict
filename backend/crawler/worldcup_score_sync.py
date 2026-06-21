"""
Sync World Cup live / finished scores from football-data.org into Match rows.

Uses an in-memory cache so API requests stay fast in production (no 20s+ blocking).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.football_data_client import (
    _api_key,
    fetch_competition_matches,
    map_match_status,
)
from crawler.the_odds_api_client import _teams_match
from data.competitions import get_competition
from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING
from data.match_status import MATCH_FINISH_BUFFER, effective_kickoff_naive
from db.models import Match
from utils.datetime_helpers import china_now
from utils.logger import logger

WC_FD_CODE = "WC"
WC_SEASON = 2026
_KICKOFF_TOLERANCE = timedelta(hours=4)
_FD_CACHE_TTL_SEC = 45

_fd_cache: list[dict] = []
_fd_cache_at: float = 0.0
_fd_refresh_lock = asyncio.Lock()
_fd_refresh_running = False


def fd_cache_age_sec() -> float:
    if not _fd_cache:
        return 1e9
    return time.monotonic() - _fd_cache_at


def schedule_fd_cache_refresh() -> None:
    """Refresh football-data cache in background (non-blocking for HTTP handlers)."""
    global _fd_refresh_running
    if _fd_refresh_running or not _api_key():
        return
    if fd_cache_age_sec() < _FD_CACHE_TTL_SEC:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(refresh_fd_cache())


async def refresh_fd_cache() -> list[dict]:
    """Fetch recent WC fixtures from football-data.org into module cache."""
    global _fd_cache, _fd_cache_at, _fd_refresh_running

    if not _api_key():
        return []

    async with _fd_refresh_lock:
        if fd_cache_age_sec() < _FD_CACHE_TTL_SEC and _fd_cache:
            return _fd_cache
        _fd_refresh_running = True
        try:
            today = china_now().date()
            rows = await fetch_competition_matches(
                WC_FD_CODE,
                WC_SEASON,
                date_from=today - timedelta(days=2),
                date_to=today + timedelta(days=1),
            )
            _fd_cache = rows
            _fd_cache_at = time.monotonic()
            logger.info("World Cup FD cache refreshed: %d fixtures", len(rows))
            return rows
        except Exception as exc:
            logger.warning("World Cup FD cache refresh failed: %s", exc)
            return _fd_cache
        finally:
            _fd_refresh_running = False


def _perspective_scores(row: dict, team_a_is_home: bool) -> tuple[int | None, int | None]:
    ra, rb = row.get("result_a"), row.get("result_b")
    if ra is None or rb is None:
        return None, None
    if team_a_is_home:
        return int(ra), int(rb)
    return int(rb), int(ra)


def _kickoff_delta(db_time: datetime | None, api_time: datetime | None) -> timedelta | None:
    if not db_time or not api_time:
        return None
    return abs(db_time - api_time)


def _find_db_match(rows: list[Match], fd_row: dict) -> tuple[Match | None, bool]:
    home_en = fd_row.get("home_name_en") or ""
    away_en = fd_row.get("away_name_en") or ""
    kickoff = fd_row.get("kickoff_beijing")

    best: Match | None = None
    best_home = True
    best_delta = _KICKOFF_TOLERANCE + timedelta(seconds=1)

    for m in rows:
        ok, a_is_home = _teams_match(m.team_a, m.team_b, home_en, away_en)
        if not ok:
            continue
        delta = _kickoff_delta(m.match_time, kickoff)
        if delta is None or delta > _KICKOFF_TOLERANCE:
            continue
        if delta <= best_delta:
            best_delta = delta
            best = m
            best_home = a_is_home
    return best, best_home


async def _apply_fd_rows(db: AsyncSession, fd_rows: list[dict]) -> dict:
    if not fd_rows:
        return {"status": "skipped", "reason": "empty_cache", "updated": 0}

    now = china_now().replace(tzinfo=None)
    lookback = now - timedelta(days=3)
    db_rows = list((await db.execute(
        select(Match).where(
            Match.competition_slug == "worldcup-2026",
            Match.match_time.isnot(None),
            Match.match_time >= lookback,
        )
    )).scalars().all())

    updated = live = finished = 0
    for fd in fd_rows:
        match, a_is_home = _find_db_match(db_rows, fd)
        if not match:
            continue

        status = map_match_status(fd.get("status_raw"))
        ra, rb = _perspective_scores(fd, a_is_home)

        kickoff = effective_kickoff_naive(match) or match.match_time
        if (
            status == MATCH_FINISHED
            and (ra is None or rb is None)
            and kickoff
            and now < kickoff + MATCH_FINISH_BUFFER
        ):
            status = MATCH_UPCOMING

        changed = False
        if status != MATCH_UPCOMING and match.status != status:
            match.status = status
            changed = True
        if ra is not None and rb is not None:
            if match.result_a != ra or match.result_b != rb:
                match.result_a = ra
                match.result_b = rb
                changed = True
        ext_id = fd.get("external_id")
        if ext_id and match.external_id != str(ext_id):
            match.external_id = str(ext_id)
            changed = True

        if not changed:
            continue
        updated += 1
        if status == MATCH_LIVE:
            live += 1
        elif status == MATCH_FINISHED:
            finished += 1

    if updated:
        await db.flush()
        logger.info(
            "World Cup score sync: updated=%d live=%d finished=%d (cache_age=%.0fs)",
            updated, live, finished, fd_cache_age_sec(),
        )
    return {
        "status": "success",
        "source": "football-data.org",
        "fd_rows": len(fd_rows),
        "updated": updated,
        "live": live,
        "finished": finished,
    }


async def sync_worldcup_scores_from_football_data(
    db: AsyncSession,
    *,
    network: bool = False,
) -> dict:
    """
    Update DB from football-data cache.

    network=False (default for HTTP): apply cache only, schedule background refresh.
    network=True (scheduler/startup): await cache refresh then apply.
    """
    comp = get_competition("worldcup-2026")
    if not comp or comp.get("type") != "international":
        return {"status": "skipped", "reason": "not_worldcup"}

    if not _api_key():
        return {"status": "skipped", "reason": "no_football_data_api_key"}

    if network:
        await refresh_fd_cache()
    else:
        schedule_fd_cache_refresh()
        if not _fd_cache:
            await refresh_fd_cache()

    return await _apply_fd_rows(db, _fd_cache)
