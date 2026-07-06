"""
Sync World Cup live / finished scores from football-data.org into Match rows.

Uses an in-memory cache so API requests stay fast in production (no 20s+ blocking).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


def _perspective_scores(row: dict, team_a_is_home: bool) -> tuple[int | None, int | None, int | None, int | None]:
    ra, rb = row.get("result_a"), row.get("result_b")
    pa, pb = row.get("penalty_a"), row.get("penalty_b")
    if ra is None or rb is None:
        reg = (None, None)
    elif team_a_is_home:
        reg = (int(ra), int(rb))
    else:
        reg = (int(rb), int(ra))
    if pa is None or pb is None:
        pen = (None, None)
    elif team_a_is_home:
        pen = (int(pa), int(pb))
    else:
        pen = (int(pb), int(pa))
    return reg[0], reg[1], pen[0], pen[1]


def _kickoff_delta(db_time: datetime | None, api_time: datetime | None) -> timedelta | None:
    if not db_time or not api_time:
        return None
    return abs(db_time - api_time)


def _normalize_ext_id(ext_id) -> int | None:
    if ext_id is None:
        return None
    try:
        return int(ext_id)
    except (TypeError, ValueError):
        return None


def _same_fixture(m1: Match, m2: Match) -> bool:
    return tuple(sorted([m1.team_a, m1.team_b])) == tuple(sorted([m2.team_a, m2.team_b]))


def _assign_external_id(
    match: Match,
    ext_id: int,
    ext_index: dict[int, Match],
) -> bool:
    """Assign football-data fixture id; skip or transfer when duplicates conflict."""
    current = _normalize_ext_id(match.external_id)
    if current == ext_id:
        return False

    owner = ext_index.get(ext_id)
    if owner and owner.id != match.id:
        if _same_fixture(owner, match):
            keep, drop = (owner, match) if (owner.id or 0) <= (match.id or 0) else (match, owner)
            if drop is match:
                logger.debug(
                    "Skip external_id=%s for duplicate match %s (%s vs %s); kept on id=%s",
                    ext_id, match.id, match.team_a, match.team_b, keep.id,
                )
                return False
            drop.external_id = None
            ext_index.pop(ext_id, None)
        else:
            logger.warning(
                "external_id=%s already on match %s (%s vs %s); skip match %s (%s vs %s)",
                ext_id, owner.id, owner.team_a, owner.team_b,
                match.id, match.team_a, match.team_b,
            )
            return False

    match.external_id = ext_id
    ext_index[ext_id] = match
    return True


def _build_ext_index(rows: list[Match]) -> dict[int, Match]:
    index: dict[int, Match] = {}
    for row in rows:
        ext_id = _normalize_ext_id(row.external_id)
        if ext_id is None:
            continue
        existing = index.get(ext_id)
        if existing and existing.id != row.id and _same_fixture(existing, row):
            keep, drop = (existing, row) if (existing.id or 0) <= (row.id or 0) else (row, existing)
            drop.external_id = None
            index[ext_id] = keep
        else:
            index[ext_id] = row
    return index


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

    ext_index = _build_ext_index(db_rows)
    updated = live = finished = 0
    for fd in fd_rows:
        match, a_is_home = _find_db_match(db_rows, fd)
        if not match:
            continue

        status = map_match_status(fd.get("status_raw"))
        ra, rb, pa, pb = _perspective_scores(fd, a_is_home)

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
        if pa is not None and pb is not None:
            if getattr(match, "penalty_a", None) != pa or getattr(match, "penalty_b", None) != pb:
                match.penalty_a = pa
                match.penalty_b = pb
                changed = True
        ext_id = _normalize_ext_id(fd.get("external_id"))
        if ext_id is not None and _assign_external_id(match, ext_id, ext_index):
            changed = True

        if not changed:
            continue
        updated += 1
        if status == MATCH_LIVE:
            live += 1
        elif status == MATCH_FINISHED:
            finished += 1

    if updated:
        try:
            from db.sqlite_write import flush_session
            await flush_session(db)
        except IntegrityError as exc:
            await db.rollback()
            logger.warning("World Cup score sync flush failed (duplicate external_id): %s", exc)
            return {"status": "failed", "error": "integrity_error", "updated": 0}
        except Exception as exc:
            await db.rollback()
            logger.warning("World Cup score sync flush failed: %s", exc)
            return {"status": "failed", "error": str(exc), "updated": 0}
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
            # Read path must not block on football-data.org; background task fills cache.
            return {"status": "skipped", "reason": "cache_empty", "updated": 0}

    return await _apply_fd_rows(db, _fd_cache)
