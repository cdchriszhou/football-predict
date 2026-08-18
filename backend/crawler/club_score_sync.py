"""Sync club-league live/finished scores from football-data.org into Match rows."""
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
    normalize_ext_id,
    perspective_scores,
)
from data.club_name_map import resolve_club_cn
from data.competitions import get_competition
from data.match_status import MATCH_FINISH_BUFFER, effective_kickoff_naive
from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING
from db.models import Match
from utils.datetime_helpers import china_now
from utils.logger import logger

_LOOKBACK_DAYS = 8
_AHEAD_DAYS = 1
_CACHE_TTL_SEC = 45
_KICKOFF_TOLERANCE = timedelta(hours=6)

_caches: dict[str, dict] = {}
_locks: dict[str, asyncio.Lock] = {}
_refresh_running: dict[str, bool] = {}


def _state(slug: str) -> dict:
    return _caches.setdefault(slug, {"rows": [], "at": 0.0})


def _lock(slug: str) -> asyncio.Lock:
    return _locks.setdefault(slug, asyncio.Lock())


def cache_age_sec(slug: str) -> float:
    st = _caches.get(slug)
    if not st or not st.get("rows"):
        return 1e9
    return time.monotonic() - float(st.get("at") or 0)


def schedule_club_score_refresh(slug: str) -> None:
    if _refresh_running.get(slug) or not _api_key():
        return
    if cache_age_sec(slug) < _CACHE_TTL_SEC:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(refresh_club_score_cache(slug))


async def refresh_club_score_cache(slug: str) -> list[dict]:
    st = _state(slug)
    if not _api_key():
        return st["rows"]

    async with _lock(slug):
        if cache_age_sec(slug) < _CACHE_TTL_SEC and st["rows"]:
            return st["rows"]
        _refresh_running[slug] = True
        try:
            comp = get_competition(slug)
            if not comp or comp.get("type") != "club":
                return []
            fd_code = comp.get("football_data_code")
            season_year = int(comp.get("season_year") or datetime.now().year)
            if not fd_code:
                return []
            today = china_now().date()
            rows = await fetch_competition_matches(
                fd_code,
                season_year,
                date_from=today - timedelta(days=_LOOKBACK_DAYS),
                date_to=today + timedelta(days=_AHEAD_DAYS),
            )
            st["rows"] = rows
            st["at"] = time.monotonic()
            logger.info("Club FD score cache [%s]: %d fixtures", slug, len(rows))
            return rows
        except Exception as exc:
            logger.warning("Club FD score cache refresh failed [%s]: %s", slug, exc)
            return st["rows"]
        finally:
            _refresh_running[slug] = False


def find_club_match(rows: list[Match], fd_row: dict) -> tuple[Match | None, bool]:
    """Locate DB fixture for a football-data row. Prefer external_id, then names."""
    ext_id = normalize_ext_id(fd_row.get("external_id"))
    home = resolve_club_cn(fd_id=fd_row.get("home_id"), name_en=fd_row.get("home_name_en"))
    away = resolve_club_cn(fd_id=fd_row.get("away_id"), name_en=fd_row.get("away_name_en"))
    kickoff = fd_row.get("kickoff_beijing") or fd_row.get("utc_date")

    if ext_id is not None:
        for m in rows:
            if normalize_ext_id(getattr(m, "external_id", None)) == ext_id:
                a_is_home = True
                if home in (m.team_a, m.team_b):
                    a_is_home = m.team_a == home
                return m, a_is_home

    if not home or not away:
        return None, True

    best: Match | None = None
    best_home = True
    best_delta = _KICKOFF_TOLERANCE.total_seconds() + 1
    name_hits: list[Match] = []
    for m in rows:
        if {m.team_a, m.team_b} != {home, away}:
            continue
        name_hits.append(m)
        mt = getattr(m, "match_time", None)
        if mt is None or kickoff is None:
            continue
        try:
            delta = abs((mt - kickoff).total_seconds())
        except TypeError:
            continue
        if delta <= best_delta:
            best_delta = delta
            best = m
            best_home = m.team_a == home
    if best is not None and best_delta <= _KICKOFF_TOLERANCE.total_seconds():
        return best, best_home
    if len(name_hits) == 1:
        m = name_hits[0]
        return m, m.team_a == home
    return None, True


def apply_club_fd_scores(matches: list[Match], fd_rows: list[dict]) -> dict:
    """Mutate match rows with live/finished scores. Returns update counts."""
    now = china_now().replace(tzinfo=None)
    updated = live = finished = 0
    for fd in fd_rows:
        match, a_is_home = find_club_match(matches, fd)
        if not match:
            continue
        status = map_match_status(fd.get("status_raw"))
        ra, rb, pa, pb = perspective_scores(fd, a_is_home)
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
        if ra is not None and rb is not None and (match.result_a != ra or match.result_b != rb):
            match.result_a = ra
            match.result_b = rb
            changed = True
        if pa is not None and pb is not None:
            if getattr(match, "penalty_a", None) != pa or getattr(match, "penalty_b", None) != pb:
                match.penalty_a = pa
                match.penalty_b = pb
                changed = True
        ext_id = normalize_ext_id(fd.get("external_id"))
        if ext_id is not None and normalize_ext_id(getattr(match, "external_id", None)) != ext_id:
            match.external_id = ext_id
            changed = True
        if not changed:
            continue
        updated += 1
        if status == MATCH_LIVE:
            live += 1
        elif status == MATCH_FINISHED:
            finished += 1
    return {"updated": updated, "live": live, "finished": finished}


async def _apply_fd_rows(db: AsyncSession, slug: str, fd_rows: list[dict]) -> dict:
    if not fd_rows:
        return {"status": "skipped", "reason": "empty_cache", "updated": 0}

    now = china_now().replace(tzinfo=None)
    lookback = now - timedelta(days=_LOOKBACK_DAYS)
    db_rows = list((await db.execute(
        select(Match).where(
            Match.competition_slug == slug,
            Match.match_time.isnot(None),
            Match.match_time >= lookback,
        )
    )).scalars().all())

    stats = apply_club_fd_scores(db_rows, fd_rows)
    updated = int(stats["updated"])
    if updated:
        try:
            from db.sqlite_write import flush_session
            await flush_session(db)
        except IntegrityError as exc:
            await db.rollback()
            logger.warning("Club score sync flush failed [%s]: %s", slug, exc)
            return {"status": "failed", "error": "integrity_error", "updated": 0}
        except Exception as exc:
            await db.rollback()
            logger.warning("Club score sync flush failed [%s]: %s", slug, exc)
            return {"status": "failed", "error": str(exc), "updated": 0}
        logger.info(
            "Club score sync [%s]: updated=%d live=%d finished=%d (cache_age=%.0fs)",
            slug, updated, stats["live"], stats["finished"], cache_age_sec(slug),
        )
    return {
        "status": "success",
        "source": "football-data.org",
        "fd_rows": len(fd_rows),
        **stats,
    }


async def sync_club_scores_from_football_data(
    db: AsyncSession,
    slug: str,
    *,
    network: bool = False,
) -> dict:
    """Update club fixtures from football-data cache (live + recently finished)."""
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return {"status": "skipped", "reason": "not_club"}
    if not _api_key():
        return {"status": "skipped", "reason": "no_football_data_api_key"}

    if network or not _state(slug)["rows"]:
        await refresh_club_score_cache(slug)
    else:
        schedule_club_score_refresh(slug)

    return await _apply_fd_rows(db, slug, _state(slug)["rows"])
