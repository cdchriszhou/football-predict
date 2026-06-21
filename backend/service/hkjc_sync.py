"""Sync HKJC official public data into local cache."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.sqlite_write import commit_session, write_lock

from crawler.hkjc_client import (
    HkjcClient,
    HKJC_RACING_BASE,
    distance_category,
    meeting_id_from,
)
from crawler.hkjc_scraper import (
    enrich_meeting_from_racecard_html,
    VENUE_LABELS,
    discover_meetings,
    fetch_meeting_with_graphql_fallback,
    parse_results_all_dates,
    resolve_venue_for_date,
)
from db.models import HkjcMeetingCache, HkjcRaceResult
from utils.logger import logger

HK_TZ = ZoneInfo("Asia/Hong_Kong")
MEETING_TTL = timedelta(minutes=5)
RESULT_TTL = timedelta(hours=12)
DISCOVER_MEETING_LIMIT = 25
MEETING_LIST_PAST_DAYS = 7
MEETING_LIST_FUTURE_DAYS = 7

def _format_meeting_label(date_str: str, venue: str) -> str:
    parts = (date_str or "").split("-")
    if len(parts) == 3:
        md = f"{int(parts[1])}/{int(parts[2])}"
    else:
        md = date_str or ""
    return f"{md} {venue}".strip()


def build_schedule_context(
    meetings: list[dict],
    recent_meeting: dict | None,
) -> dict:
    """HK-local calendar hints for dashboard UI."""
    today = datetime.now(HK_TZ).date()
    today_str = today.isoformat()
    today_label = f"{today.month}/{today.day}"

    dates_venues: dict[str, str] = {}
    for m in meetings:
        d = m.get("date")
        if d:
            dates_venues[d] = m.get("venue") or dates_venues.get(d, "")
    if recent_meeting and recent_meeting.get("date"):
        d = recent_meeting["date"]
        dates_venues.setdefault(d, recent_meeting.get("venue") or "")

    has_today = today_str in dates_venues
    recent_src = recent_meeting or (meetings[0] if meetings else None)
    recent_label = None
    if recent_src and recent_src.get("date"):
        recent_label = _format_meeting_label(
            recent_src["date"],
            recent_src.get("venue") or "",
        )

    return {
        "today_hk": today_str,
        "today_label": today_label,
        "has_meeting_today": has_today,
        "today_venue": dates_venues.get(today_str) if has_today else None,
        "recent_meeting_label": recent_label,
    }


def _json_loads(raw: str) -> dict:
    return json.loads(raw) if raw else {}


async def _commit_with_retry(db: AsyncSession) -> None:
    await commit_session(db)


async def _release_read_transaction(db: AsyncSession) -> None:
    """End implicit read transaction before long network I/O."""
    try:
        await db.commit()
    except Exception:
        await db.rollback()


def _meeting_summary(meeting: dict) -> dict:
    return {
        "id": meeting["id"],
        "date": meeting["date"],
        "venue": meeting["venue"],
        "venue_en": meeting.get("venue_en"),
        "venue_code": meeting.get("venue_code"),
        "track_type": meeting.get("track_type"),
        "track_rating": meeting.get("track_rating"),
        "weather": meeting.get("weather", ""),
        "temperature_c": meeting.get("temperature_c"),
        "race_count": meeting.get("race_count", 0),
        "meeting_risk": meeting.get("meeting_risk", "medium"),
        "featured": meeting.get("featured", False),
        "status": meeting.get("status", ""),
        "synced_at": meeting.get("synced_at"),
    }


def _apply_meeting_status(summary: dict, result_ids: set[str]) -> dict:
    mid = summary.get("id") or ""
    explicit = (summary.get("status") or "").upper()
    if mid in result_ids or explicit == "RESULTS":
        summary["status"] = "RESULTS"
        return summary
    date_str = summary.get("date") or ""
    try:
        md = date.fromisoformat(date_str)
    except ValueError:
        summary["status"] = explicit or "UNKNOWN"
        return summary
    today = datetime.now(HK_TZ).date()
    if explicit == "SCHEDULED" and md >= today:
        summary["status"] = "SCHEDULED"
        return summary
    if md > today:
        summary["status"] = explicit if explicit in ("UPCOMING", "SCHEDULED") else "UPCOMING"
    elif md == today:
        summary["status"] = explicit if explicit in ("ACTIVE", "UPCOMING") else "ACTIVE"
    else:
        summary["status"] = "RESULTS" if mid in result_ids else "PAST"
    return summary


def _sort_meeting_summaries(items: list[dict]) -> list[dict]:
    upcoming = [m for m in items if m.get("status") in ("UPCOMING", "ACTIVE", "SCHEDULED")]
    finished = [m for m in items if m.get("status") == "RESULTS"]
    other = [m for m in items if m not in upcoming and m not in finished]
    upcoming.sort(key=lambda m: m.get("date") or "")
    finished.sort(key=lambda m: m.get("date") or "", reverse=True)
    other.sort(key=lambda m: m.get("date") or "", reverse=True)
    return upcoming + other + finished


def _filter_meetings_by_window(
    items: list[dict],
    *,
    past_days: int = MEETING_LIST_PAST_DAYS,
    future_days: int = MEETING_LIST_FUTURE_DAYS,
) -> list[dict]:
    """Show completed meetings from the past week and upcoming within the next week."""
    today = datetime.now(HK_TZ).date()
    start = today - timedelta(days=past_days)
    end = today + timedelta(days=future_days)
    filtered: list[dict] = []
    for m in items:
        try:
            md = date.fromisoformat(m.get("date") or "")
        except ValueError:
            continue
        if start <= md <= end:
            filtered.append(m)
    return _sort_meeting_summaries(filtered)


async def _result_meeting_ids(db: AsyncSession) -> set[str]:
    rows = (await db.execute(
        select(HkjcRaceResult.meeting_date, HkjcRaceResult.venue_code).distinct()
    )).all()
    await _release_read_transaction(db)
    return {meeting_id_from(r[0], r[1]) for r in rows}


def _tag_meeting_status(meeting: dict) -> dict:
    """Set status on a full meeting payload before save."""
    today = datetime.now(HK_TZ).date()
    try:
        md = date.fromisoformat(meeting.get("date") or "")
    except ValueError:
        return meeting
    explicit = (meeting.get("status") or "").upper()
    if explicit == "RESULTS" or meeting.get("source") == "hkjc_results":
        meeting["status"] = "RESULTS"
    elif explicit == "SCHEDULED" or meeting.get("source") == "hkjc_scheduled":
        meeting["status"] = "SCHEDULED"
    elif md > today:
        meeting["status"] = "UPCOMING"
    elif md == today:
        meeting["status"] = "ACTIVE" if meeting.get("featured") else "UPCOMING"
    return meeting


def _scheduled_meeting_stub(meeting_date: str, venue_code: str) -> dict:
    venue_code = venue_code.upper()
    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    meeting_id = meeting_id_from(meeting_date, venue_code)
    return {
        "id": meeting_id,
        "date": meeting_date,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "track_type": "",
        "track_rating": "",
        "weather": "",
        "temperature_c": None,
        "race_count": 0,
        "meeting_risk": "medium",
        "featured": False,
        "status": "SCHEDULED",
        "races": [],
        "horses_index": [],
        "source": "hkjc_scheduled",
    }


async def _save_meeting(db: AsyncSession, meeting: dict, source: str = "hkjc_graphql") -> None:
    now = datetime.utcnow()
    meeting = _tag_meeting_status(dict(meeting))
    meeting["synced_at"] = now.isoformat() + "Z"
    row = HkjcMeetingCache(
        id=meeting["id"],
        meeting_date=meeting["date"],
        venue_code=meeting.get("venue_code") or "",
        payload=json.dumps(meeting, ensure_ascii=False),
        source=source,
        synced_at=now,
    )
    await db.merge(row)


async def _load_meeting_row(db: AsyncSession, meeting_id: str) -> dict | None:
    row = await db.get(HkjcMeetingCache, meeting_id)
    if not row:
        return None
    data = _json_loads(row.payload)
    data["synced_at"] = row.synced_at.isoformat() + "Z" if row.synced_at else None
    data["source"] = row.source
    return data


async def _is_meeting_stale(db: AsyncSession, meeting_id: str) -> bool:
    row = await db.get(HkjcMeetingCache, meeting_id)
    if not row or not row.synced_at:
        return True
    return datetime.utcnow() - row.synced_at.replace(tzinfo=None) > MEETING_TTL


async def _fetch_meeting_remote(meeting_date: str, venue_code: str) -> dict | None:
    """Network-only fetch — must not hold a DB transaction."""
    client = HkjcClient()
    try:
        return await fetch_meeting_with_graphql_fallback(client, meeting_date, venue_code)
    except Exception as e:
        logger.warning(f"HKJC meeting fetch failed {meeting_date}/{venue_code}: {e}")
        return None


async def sync_meeting_from_api(
    db: AsyncSession,
    meeting_date: str,
    venue_code: str,
    *,
    force: bool = False,
    commit: bool = False,
) -> dict | None:
    meeting_id = meeting_id_from(meeting_date, venue_code)
    cached: dict | None = None

    if not force:
        cached = await _load_meeting_row(db, meeting_id)
        if cached and not await _is_meeting_stale(db, meeting_id):
            await _release_read_transaction(db)
            return cached

    await _release_read_transaction(db)

    meeting = await _fetch_meeting_remote(meeting_date, venue_code)
    if not meeting:
        return cached

    source = meeting.get("source") or "hkjc_html"
    await _save_meeting(db, meeting, source=source)
    if commit:
        await _commit_with_retry(db)
    return meeting


async def sync_active_meetings(
    db: AsyncSession,
    *,
    force: bool = False,
    commit: bool = True,
) -> list[dict]:
    """Sync meetings; release DB lock while fetching HKJC over the network."""
    client = HkjcClient()
    summaries: list[dict] = []
    to_fetch: list[tuple[str, str]] = []
    seen: set[str] = set()

    try:
        discovered = await discover_meetings(client, limit=DISCOVER_MEETING_LIMIT)
    except Exception as e:
        logger.warning(f"HKJC discover meetings failed: {e}")
        discovered = []

    async with write_lock:
        for item in discovered:
            status = (item.get("status") or "").upper()
            try:
                md = date.fromisoformat(item.get("date") or "")
            except ValueError:
                continue
            today = datetime.now(HK_TZ).date()
            if status in ("UPCOMING", "SCHEDULED", "ACTIVE") or md >= today:
                await _save_discovered_stub(db, item)
        if commit:
            await _commit_with_retry(db)

    for item in discovered:
        d = item.get("date") or ""
        vc = (item.get("venue_code") or "").upper()
        if d and vc:
            key = meeting_id_from(d, vc)
            if key not in seen:
                seen.add(key)
                to_fetch.append((d, vc))

    if not to_fetch:
        try:
            all_html = await client.fetch_html(f"{HKJC_RACING_BASE}/ResultsAll.aspx")
            for d in parse_results_all_dates(all_html, limit=DISCOVER_MEETING_LIMIT):
                vc = await resolve_venue_for_date(client, d)
                if not vc:
                    continue
                key = meeting_id_from(d, vc)
                if key not in seen:
                    seen.add(key)
                    to_fetch.append((d, vc))
        except Exception as e:
            logger.warning(f"HKJC ResultsAll fallback failed: {e}")

    saved: list[dict] = []
    for d, vc in to_fetch:
        meeting_id = meeting_id_from(d, vc)
        if not force:
            async with write_lock:
                cached = await _load_meeting_row(db, meeting_id)
                stale = True
                if cached:
                    stale = await _is_meeting_stale(db, meeting_id)
                await _release_read_transaction(db)
            if cached and not stale:
                saved.append(cached)
                continue

        meeting = await _fetch_meeting_remote(d, vc)
        if not meeting or meeting.get("race_count", 0) <= 0:
            try:
                md = date.fromisoformat(d)
                if md >= datetime.now(HK_TZ).date():
                    meeting = _scheduled_meeting_stub(d, vc)
                else:
                    continue
            except ValueError:
                continue
        source = meeting.get("source") or "hkjc_html"
        async with write_lock:
            await _save_meeting(db, meeting, source=source)
            if commit:
                await _commit_with_retry(db)
        saved.append(meeting)

    if saved:
        seen_summary: set[str] = set()
        for meeting in saved:
            mid = meeting["id"]
            if mid in seen_summary:
                continue
            seen_summary.add(mid)
            summaries.append(_meeting_summary(meeting))
        return sorted(summaries, key=lambda x: x.get("date") or "", reverse=True)

    async with write_lock:
        rows = (await db.execute(
            select(HkjcMeetingCache).order_by(HkjcMeetingCache.meeting_date.desc())
        )).scalars().all()
        await _release_read_transaction(db)
    for row in rows[:10]:
        data = _json_loads(row.payload)
        summaries.append(_meeting_summary(data))
    return summaries


def _summary_from_result_group(meeting_date: str, venue_code: str, race_count: int) -> dict:
    venue_code = venue_code.upper()
    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    return {
        "id": meeting_id_from(meeting_date, venue_code),
        "date": meeting_date,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "track_type": "",
        "track_rating": "",
        "weather": "",
        "temperature_c": None,
        "race_count": race_count,
        "meeting_risk": "medium",
        "featured": False,
        "status": "RESULTS",
        "synced_at": None,
    }


async def _summaries_from_stored_results(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(HkjcRaceResult).order_by(
            HkjcRaceResult.meeting_date.desc(),
            HkjcRaceResult.venue_code,
            HkjcRaceResult.race_no,
        )
    )).scalars().all()
    await _release_read_transaction(db)
    counts: dict[str, tuple[str, str, int]] = {}
    for row in rows:
        key = meeting_id_from(row.meeting_date, row.venue_code)
        if key not in counts:
            counts[key] = (row.meeting_date, row.venue_code, 0)
        d, vc, n = counts[key]
        counts[key] = (d, vc, n + 1)
    return [
        _summary_from_result_group(d, vc, n)
        for d, vc, n in counts.values()
    ]


def _merge_meeting_summaries(cache: list[dict], results: list[dict], result_ids: set[str]) -> list[dict]:
    merged: dict[str, dict] = {m["id"]: m for m in results if m.get("id")}
    today = datetime.now(HK_TZ).date()
    for item in cache:
        mid = item.get("id")
        if not mid:
            continue
        existing = merged.get(mid)
        if not existing:
            merged[mid] = item
            continue
        try:
            md = date.fromisoformat(item.get("date") or "")
        except ValueError:
            md = None
        if md and md >= today and item.get("status") not in ("RESULTS", "PAST"):
            merged[mid] = item
        elif (item.get("race_count") or 0) > (existing.get("race_count") or 0):
            merged[mid] = item
    enriched = [_apply_meeting_status(dict(m), result_ids) for m in merged.values()]
    return _sort_meeting_summaries(enriched)


def _normalize_discovered_item(item: dict) -> dict | None:
    d = item.get("date") or ""
    vc = (item.get("venue_code") or "").upper()
    if not d or not vc:
        return None
    venue_zh, venue_en = VENUE_LABELS.get(vc, (vc, vc))
    return {
        "id": item.get("id") or meeting_id_from(d, vc),
        "date": d,
        "venue": item.get("venue") or venue_zh,
        "venue_en": item.get("venue_en") or venue_en,
        "venue_code": vc,
        "race_count": int(item.get("race_count") or item.get("race_count_hint") or 0),
        "status": (item.get("status") or "UPCOMING").upper(),
        "featured": bool(item.get("featured")),
        "track_type": item.get("track_type") or "",
        "track_rating": item.get("track_rating") or "",
    }


async def _save_discovered_stub(db: AsyncSession, item: dict) -> bool:
    """Persist upcoming/active meeting stub so it appears in meeting lists."""
    norm = _normalize_discovered_item(item)
    if not norm:
        return False
    try:
        md = date.fromisoformat(norm["date"])
    except ValueError:
        return False
    today = datetime.now(HK_TZ).date()
    if md < today - timedelta(days=1):
        return False

    cached = await _load_meeting_row(db, norm["id"])
    await _release_read_transaction(db)
    if cached:
        cached_races = len(cached.get("races") or [])
        if cached_races > 0 and norm["race_count"] <= cached.get("race_count", 0):
            return False

    meeting = dict(cached) if cached else _scheduled_meeting_stub(norm["date"], norm["venue_code"])
    meeting.update({
        "id": norm["id"],
        "date": norm["date"],
        "venue": norm["venue"],
        "venue_en": norm["venue_en"],
        "venue_code": norm["venue_code"],
        "race_count": max(int(meeting.get("race_count") or 0), norm["race_count"]),
        "status": norm["status"],
        "featured": norm["featured"] or meeting.get("featured", False),
    })
    if norm.get("track_type"):
        meeting["track_type"] = norm["track_type"]
    if norm.get("track_rating"):
        meeting["track_rating"] = norm["track_rating"]
    await _save_meeting(db, meeting, source="hkjc_discovery")
    return True


async def append_discovered_meeting_stubs(db: AsyncSession, *, commit: bool = True) -> int:
    """Lightweight discovery: ensure future meeting days exist in cache."""
    client = HkjcClient()
    try:
        discovered = await discover_meetings(client, limit=DISCOVER_MEETING_LIMIT)
    except Exception as e:
        logger.warning(f"HKJC discovery stubs failed: {e}")
        return 0

    saved = 0
    async with write_lock:
        for item in discovered:
            status = (item.get("status") or "").upper()
            try:
                md = date.fromisoformat(item.get("date") or "")
            except ValueError:
                continue
            today = datetime.now(HK_TZ).date()
            if status == "RESULTS" and md < today:
                continue
            if status in ("UPCOMING", "SCHEDULED", "ACTIVE") or md >= today:
                if await _save_discovered_stub(db, item):
                    saved += 1
        if commit and saved:
            await _commit_with_retry(db)
    return saved


async def _has_upcoming_cached(db: AsyncSession) -> bool:
    today = datetime.now(HK_TZ).date().isoformat()
    row = (await db.execute(
        select(HkjcMeetingCache.id)
        .where(HkjcMeetingCache.meeting_date >= today)
        .limit(1)
    )).scalar()
    await _release_read_transaction(db)
    return row is not None


async def get_hkjc_competition_stats(db: AsyncSession, *, light: bool = False) -> dict:
    """Stats for competition picker card (meetings / races / horses).

    light=True: cache-only counts for GET /competitions (no HKJC network, no full horse merge).
    """
    if not light and not await _has_upcoming_cached(db):
        try:
            await append_discovered_meeting_stubs(db, commit=True)
        except Exception as e:
            logger.warning(f"HKJC discovery stubs for stats failed: {e}")

    rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
    await _release_read_transaction(db)
    today = datetime.now(HK_TZ).date().isoformat()
    meeting_count = 0
    race_total = 0
    upcoming = live = finished = 0
    horse_codes: set[str] = set()
    for row in rows:
        data = _json_loads(row.payload)
        meeting_count += 1
        race_total += int(data.get("race_count") or len(data.get("races") or []))
        status = (data.get("status") or "").upper()
        d = data.get("date") or ""
        if status in ("UPCOMING", "SCHEDULED") or d >= today:
            upcoming += 1
        if status == "ACTIVE":
            live += 1
        if status in ("RESULTS", "PAST"):
            finished += 1
        if light:
            for h in data.get("horses_index") or []:
                code = h.get("horse_code") or h.get("name")
                if code:
                    horse_codes.add(code)
            if not horse_codes:
                for race in data.get("races") or []:
                    for r in race.get("runners") or []:
                        code = r.get("horse_code") or r.get("name")
                        if code:
                            horse_codes.add(code)

    if light:
        team_count = len(horse_codes)
    else:
        horses = await list_horses(db)
        team_count = len(horses)
    return {
        "matches": race_total,
        "teams": team_count,
        "upcoming": upcoming,
        "live": live,
        "finished": finished,
        "meetings": meeting_count,
    }


def _build_meeting_from_result_rows(rows: list[HkjcRaceResult]) -> dict | None:
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r.race_no)
    races = []
    horses_index: dict[str, dict] = {}
    for row in rows:
        result = _json_loads(row.payload)
        race = result_to_race_payload(result)
        races.append(race)
        for runner in race.get("runners") or []:
            code = runner.get("name") or str(runner.get("horse_no"))
            if code and code not in horses_index:
                horses_index[code] = {
                    "name": runner.get("name"),
                    "rating": runner.get("rating", 0),
                    "age": runner.get("age", 0),
                    "sex": runner.get("sex", ""),
                    "trainer": runner.get("trainer", ""),
                    "recent_form": runner.get("recent_form", ""),
                    "horse_code": code,
                }
    meeting_date = rows[0].meeting_date
    venue_code = rows[0].venue_code.upper()
    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    meeting_id = meeting_id_from(meeting_date, venue_code)
    return {
        "id": meeting_id,
        "date": meeting_date,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "track_type": races[0].get("track_type", "草地") if races else "草地",
        "track_rating": races[0].get("going", "") if races else "",
        "weather": "",
        "temperature_c": None,
        "race_count": len(races),
        "meeting_risk": "medium",
        "featured": False,
        "status": "RESULTS",
        "races": races,
        "horses_index": sorted(horses_index.values(), key=lambda h: -h.get("rating", 0)),
        "source": "hkjc_results",
    }


async def sync_meetings_from_stored_results(
    db: AsyncSession,
    *,
    commit: bool = True,
) -> int:
    """Upsert meeting cache entries from already-synced LocalResults rows."""
    rows = (await db.execute(select(HkjcRaceResult))).scalars().all()
    await _release_read_transaction(db)
    groups: dict[str, list[HkjcRaceResult]] = {}
    for row in rows:
        key = meeting_id_from(row.meeting_date, row.venue_code)
        groups.setdefault(key, []).append(row)

    saved = 0
    for mid, group_rows in groups.items():
        cached = await _load_meeting_row(db, mid)
        await _release_read_transaction(db)
        if cached:
            src = (cached.get("source") or "").lower()
            # Keep racecard/graphql cache; result-page merge must not downgrade backtest input.
            if src not in ("hkjc_results",):
                continue
            if len(cached.get("races") or []) >= len(group_rows):
                continue
        meeting = _build_meeting_from_result_rows(group_rows)
        if not meeting:
            continue
        await _save_meeting(db, meeting, source="hkjc_results")
        saved += 1

    if commit and saved:
        await _commit_with_retry(db)
    return saved


async def list_meetings(
    db: AsyncSession,
    *,
    refresh: bool = False,
    past_days: int = MEETING_LIST_PAST_DAYS,
    future_days: int = MEETING_LIST_FUTURE_DAYS,
) -> list[dict]:
    """List meeting summaries. refresh=True only re-discovers stubs (not full HKJC sync)."""
    if refresh:
        try:
            await append_discovered_meeting_stubs(db, commit=True)
            await sync_meetings_from_stored_results(db, commit=True)
        except Exception as e:
            logger.warning(f"HKJC meetings refresh failed: {e}")
    else:
        cache_count = (await db.execute(select(HkjcMeetingCache.id).limit(1))).scalar()
        result_count = (await db.execute(select(HkjcRaceResult.id).limit(1))).scalar()
        await _release_read_transaction(db)
        if not cache_count and not result_count:
            try:
                await sync_active_meetings(db, force=False, commit=True)
                await sync_meetings_from_stored_results(db, commit=True)
            except Exception as e:
                logger.warning(f"HKJC sync active failed: {e}")
        elif not await _has_upcoming_cached(db):
            try:
                await append_discovered_meeting_stubs(db, commit=True)
            except Exception as e:
                logger.warning(f"HKJC discovery stubs failed: {e}")

    rows = (await db.execute(
        select(HkjcMeetingCache).order_by(HkjcMeetingCache.meeting_date.desc())
    )).scalars().all()
    await _release_read_transaction(db)

    cache_summaries = [_meeting_summary(_json_loads(r.payload)) for r in rows]
    result_summaries = await _summaries_from_stored_results(db)
    result_ids = await _result_meeting_ids(db)
    merged = _merge_meeting_summaries(cache_summaries, result_summaries, result_ids)
    return _filter_meetings_by_window(merged, past_days=past_days, future_days=future_days)


async def get_meeting(db: AsyncSession, meeting_id: str, *, refresh: bool = False) -> dict | None:
    if not refresh:
        cached = await _load_meeting_row(db, meeting_id)
        stale = await _is_meeting_stale(db, meeting_id)
        await _release_read_transaction(db)
        if cached and not stale:
            return _meeting_detail(cached)

    parts = meeting_id.rsplit("-", 1)
    if len(parts) != 2:
        return await _load_meeting_detail(db, meeting_id)
    date_part, venue = parts
    if len(date_part) == 8:
        meeting_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    else:
        meeting_date = date_part
    meeting = await sync_meeting_from_api(
        db, meeting_date, venue.upper(), force=refresh, commit=True
    )
    return _meeting_detail(meeting) if meeting else None


def _meeting_detail(meeting: dict | None) -> dict | None:
    if not meeting:
        return None
    races = meeting.get("races") or []
    return {
        **_meeting_summary(meeting),
        "status": meeting.get("status") or "UNKNOWN",
        "races": [{
            "id": r["id"],
            "race_no": r["race_no"],
            "name": r["name"],
            "distance_m": r["distance_m"],
            "class": r["class"],
            "start_time": r["start_time"],
            "risk_level": r["risk_level"],
            "runner_count": len(r.get("runners") or []),
        } for r in races],
    }


async def _load_meeting_detail(db: AsyncSession, meeting_id: str) -> dict | None:
    data = await _load_meeting_row(db, meeting_id)
    await _release_read_transaction(db)
    return _meeting_detail(data)


async def get_race(db: AsyncSession, race_id: str, *, refresh: bool = False) -> dict | None:
    meeting_id = race_id.rsplit("-r", 1)[0] if "-r" in race_id else ""
    if refresh and meeting_id:
        await get_meeting(db, meeting_id, refresh=True)
    row = await db.get(HkjcMeetingCache, meeting_id) if meeting_id else None
    if not row:
        rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
        for r in rows:
            data = _json_loads(r.payload)
            for race in data.get("races") or []:
                if race.get("id") == race_id:
                    await _release_read_transaction(db)
                    return race
        await _release_read_transaction(db)
        return None
    data = _json_loads(row.payload)
    await _release_read_transaction(db)
    for race in data.get("races") or []:
        if race.get("id") == race_id:
            return race
    return None


async def list_races_for_meeting(db: AsyncSession, meeting_id: str) -> list[dict]:
    row = await db.get(HkjcMeetingCache, meeting_id)
    if not row:
        await _release_read_transaction(db)
        return []
    data = _json_loads(row.payload)
    await _release_read_transaction(db)
    return data.get("races") or []


def _extract_race_winner(result: dict) -> dict | None:
    finishers = result.get("finishers") or []
    for f in finishers:
        if f.get("placing") == 1:
            return {
                "horse_no": f.get("horse_no"),
                "name": f.get("name"),
                "jockey": f.get("jockey"),
                "odds": f.get("odds"),
            }
    win_no = result.get("winner_horse_no")
    if win_no:
        for f in finishers:
            if f.get("horse_no") == win_no:
                return {
                    "horse_no": f.get("horse_no"),
                    "name": f.get("name"),
                    "jockey": f.get("jockey"),
                    "odds": f.get("odds"),
                }
    return None


def _venue_code_from_meeting(meeting: dict) -> str:
    code = (meeting.get("venue_code") or "").upper()
    if code:
        return code
    venue = meeting.get("venue") or ""
    if "沙田" in venue:
        return "ST"
    if "跑" in venue or "谷" in venue:
        return "HV"
    return ""


async def build_meeting_winners(
    db: AsyncSession,
    meeting: dict,
    races: list[dict],
) -> list[dict]:
    """Per-race first-place finishers for dashboard (from synced LocalResults)."""
    date = meeting.get("date") or ""
    venue_code = _venue_code_from_meeting(meeting)
    result_by_race: dict[int, dict] = {}

    if date and venue_code:
        rows = (await db.execute(
            select(HkjcRaceResult).where(
                HkjcRaceResult.meeting_date == date,
                HkjcRaceResult.venue_code == venue_code,
            )
        )).scalars().all()
        await _release_read_transaction(db)
        for row in rows:
            result = _json_loads(row.payload)
            winner = _extract_race_winner(result)
            result_by_race[int(row.race_no)] = {
                "distance_m": result.get("distance_m"),
                "class": result.get("class"),
                "winner": winner,
            }
    else:
        await _release_read_transaction(db)

    ordered = sorted(races or [], key=lambda r: r.get("race_no", 0))
    if not ordered and result_by_race:
        ordered = [{"race_no": n} for n in sorted(result_by_race.keys())]

    meeting_id = meeting.get("id") or ""
    out: list[dict] = []
    for race in ordered:
        race_no = int(race.get("race_no") or 0)
        hit = result_by_race.get(race_no) or {}
        winner = hit.get("winner")
        out.append({
            "race_id": race.get("id") or (f"{meeting_id}-r{race_no}" if meeting_id else ""),
            "race_no": race_no,
            "distance_m": race.get("distance_m") or hit.get("distance_m"),
            "class": race.get("class") or hit.get("class"),
            "winner_horse_no": winner.get("horse_no") if winner else None,
            "winner_name": winner.get("name") if winner else None,
            "winner_jockey": winner.get("jockey") if winner else None,
            "winner_odds": winner.get("odds") if winner else None,
        })
    return out


def _merge_horse_profile(target: dict, source: dict) -> None:
    """Fill missing age/sex/rating when newer racecard rows have them."""
    from crawler.hkjc_scraper import merge_runner_profile

    merge_runner_profile(target, source)


async def refresh_horse_profiles_in_cache(
    db: AsyncSession,
    *,
    max_meetings: int = 6,
    commit: bool = True,
) -> int:
    """Re-scrape RaceCard HTML for recent meetings to restore age/sex/rating."""
    client = HkjcClient()
    async with write_lock:
        rows = (
            await db.execute(
                select(HkjcMeetingCache)
                .order_by(HkjcMeetingCache.meeting_date.desc())
                .limit(max_meetings * 3)
            )
        ).scalars().all()
        await _release_read_transaction(db)

    updated = 0
    for row in rows:
        if updated >= max_meetings:
            break
        data = _json_loads(row.payload)
        if not data.get("races"):
            continue
        needs = any(
            not int(r.get("age") or 0) or not r.get("sex") or not int(r.get("rating") or 0)
            for race in data.get("races") or []
            for r in race.get("runners") or []
        )
        if not needs and data.get("horses_index"):
            hi = data["horses_index"][0] if data["horses_index"] else {}
            if int(hi.get("age") or 0) and hi.get("sex") and int(hi.get("rating") or 0):
                continue
        if not await enrich_meeting_from_racecard_html(client, data):
            continue
        async with write_lock:
            await _save_meeting(db, data, source=data.get("source") or row.source)
            updated += 1
        if commit:
            await _commit_with_retry(db)
    return updated


def _aggregate_horses_from_rows(rows: list) -> dict[str, dict]:
    horses: dict[str, dict] = {}
    for row in rows:
        data = _json_loads(row.payload)
        for h in data.get("horses_index") or []:
            code = h.get("horse_code") or h.get("name")
            if not code:
                continue
            if code not in horses:
                horses[code] = dict(h)
            else:
                _merge_horse_profile(horses[code], h)
        for race in data.get("races") or []:
            for r in race.get("runners") or []:
                code = r.get("horse_code") or r.get("name")
                if not code:
                    continue
                profile = {
                    "name": r.get("name"),
                    "rating": r.get("rating"),
                    "age": r.get("age"),
                    "sex": r.get("sex"),
                    "trainer": r.get("trainer"),
                    "recent_form": r.get("recent_form"),
                    "horse_code": r.get("horse_code"),
                }
                if code not in horses:
                    horses[code] = profile
                else:
                    _merge_horse_profile(horses[code], profile)
    return horses


def _horse_profiles_incomplete(horses: dict[str, dict]) -> bool:
    """True when the catalog is empty or most rows lack basic identity (name-only stubs)."""
    if not horses:
        return True
    usable = sum(
        1 for h in horses.values()
        if (h.get("name") or h.get("horse_code"))
        and (int(h.get("age") or 0) or h.get("sex") or int(h.get("rating") or 0))
    )
    return usable < max(1, len(horses) // 10)


def _ratings_mostly_missing(horses: dict[str, dict]) -> bool:
    if not horses:
        return False
    with_rating = sum(1 for h in horses.values() if int(h.get("rating") or 0) > 0)
    return with_rating < max(3, len(horses) // 20)


def _meeting_has_runners(meeting: dict | None) -> bool:
    if not meeting:
        return False
    return any(race.get("runners") for race in meeting.get("races") or [])


async def ensure_horse_catalog(
    db: AsyncSession,
    *,
    max_sync: int = 3,
    commit: bool = True,
) -> int:
    """When cache only has empty stubs or result-only rows, pull full racecards from HKJC."""
    try:
        await sync_meetings_from_stored_results(db, commit=commit)
    except Exception as e:
        logger.warning(f"ensure_horse_catalog results merge failed: {e}")

    rows = (await db.execute(
        select(HkjcMeetingCache).order_by(HkjcMeetingCache.meeting_date.desc()).limit(40)
    )).scalars().all()
    await _release_read_transaction(db)
    horses = _aggregate_horses_from_rows(rows)
    if horses and not _horse_profiles_incomplete(horses) and not _ratings_mostly_missing(horses):
        return 0

    synced = 0
    candidates: list[tuple[str, str]] = []
    today = datetime.now(HK_TZ).date()
    for row in rows:
        data = _json_loads(row.payload)
        d = data.get("date") or row.meeting_date
        vc = (data.get("venue_code") or row.venue_code or "").upper()
        if not d or not vc:
            continue
        try:
            md = date.fromisoformat(d)
        except ValueError:
            continue
        if md < today - timedelta(days=21) or md > today + timedelta(days=14):
            continue
        if not _meeting_has_runners(data):
            candidates.append((d, vc))
            continue
        if _horse_profiles_incomplete(horses):
            candidates.append((d, vc))
            continue
        if _ratings_mostly_missing(horses) and md >= today - timedelta(days=14):
            candidates.append((d, vc))

    if not candidates:
        try:
            await append_discovered_meeting_stubs(db, commit=commit)
        except Exception as e:
            logger.warning(f"ensure_horse_catalog discovery failed: {e}")
        discovered_rows = (await db.execute(
            select(HkjcMeetingCache).order_by(HkjcMeetingCache.meeting_date.desc()).limit(10)
        )).scalars().all()
        await _release_read_transaction(db)
        for row in discovered_rows:
            data = _json_loads(row.payload)
            d, vc = data.get("date"), (data.get("venue_code") or "").upper()
            if d and vc:
                candidates.append((d, vc))

    seen: set[str] = set()
    for meeting_date, venue_code in candidates:
        if synced >= max_sync:
            break
        mid = meeting_id_from(meeting_date, venue_code)
        if mid in seen:
            continue
        seen.add(mid)
        cached = await _load_meeting_row(db, mid)
        await _release_read_transaction(db)
        if cached and _meeting_has_runners(cached):
            row_horses = {}
            for race in cached.get("races") or []:
                for r in race.get("runners") or []:
                    code = r.get("horse_code") or r.get("name")
                    if code:
                        row_horses[code] = r
            if row_horses and not _horse_profiles_incomplete(row_horses):
                continue
        meeting = await sync_meeting_from_api(
            db, meeting_date, venue_code, force=True, commit=commit
        )
        if meeting and _meeting_has_runners(meeting):
            synced += 1
    return synced


async def list_horses(
    db: AsyncSession,
    *,
    refresh_profiles: bool = False,
    ensure: bool = False,
) -> list[dict]:
    if refresh_profiles:
        try:
            await asyncio.wait_for(
                refresh_horse_profiles_in_cache(db, max_meetings=3, commit=True),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            logger.warning("refresh_horse_profiles_in_cache timed out (refresh=true)")
    rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
    horses: dict[str, dict] = _aggregate_horses_from_rows(rows)
    if ensure:
        try:
            if not horses or _horse_profiles_incomplete(horses):
                await asyncio.wait_for(
                    ensure_horse_catalog(db, max_sync=2, commit=True),
                    timeout=180.0,
                )
                rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
                horses = _aggregate_horses_from_rows(rows)
            elif _ratings_mostly_missing(horses):
                await asyncio.wait_for(
                    refresh_horse_profiles_in_cache(db, max_meetings=2, commit=True),
                    timeout=90.0,
                )
                rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
                horses = _aggregate_horses_from_rows(rows)
            elif refresh_profiles:
                await asyncio.wait_for(
                    refresh_horse_profiles_in_cache(db, max_meetings=2, commit=True),
                    timeout=90.0,
                )
                rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
                horses = _aggregate_horses_from_rows(rows)
        except asyncio.TimeoutError:
            logger.warning("list_horses ensure/refresh timed out — returning cache")
        except Exception as e:
            logger.warning(f"list_horses ensure failed: {e}")
    await _release_read_transaction(db)
    return sorted(horses.values(), key=lambda x: -(x.get("rating") or 0))


async def sync_race_results(
    db: AsyncSession,
    *,
    days: int = 90,
    max_races_per_day: int = 11,
    commit: bool = True,
) -> int:
    """Pull official LocalResults for recent race days."""
    async with write_lock:
        existing_rows = (await db.execute(select(HkjcRaceResult))).scalars().all()
        existing_map = {r.id: r.synced_at for r in existing_rows}
        await _release_read_transaction(db)

    client = HkjcClient()
    today = datetime.now(HK_TZ).date()
    pending: list[dict] = []
    for i in range(days):
        d = today - timedelta(days=i)
        for venue in ("ST", "HV"):
            for race_no in range(1, max_races_per_day + 1):
                rid = f"{d.isoformat()}-{venue}-{race_no}"
                synced_at = existing_map.get(rid)
                if synced_at:
                    age = datetime.utcnow() - synced_at.replace(tzinfo=None)
                    if age < RESULT_TTL:
                        continue
                result = await client.fetch_race_result(d, venue, race_no)
                if not result:
                    break
                pending.append({
                    "id": rid,
                    "meeting_date": d.isoformat(),
                    "venue_code": venue,
                    "race_no": race_no,
                    "payload": json.dumps(result, ensure_ascii=False),
                })

    if not pending:
        return 0

    now = datetime.utcnow()
    async with write_lock:
        for item in pending:
            await db.merge(HkjcRaceResult(
                id=item["id"],
                meeting_date=item["meeting_date"],
                venue_code=item["venue_code"],
                race_no=item["race_no"],
                payload=item["payload"],
                synced_at=now,
            ))
        if commit:
            await _commit_with_retry(db)
    await sync_meetings_from_stored_results(db, commit=commit)
    return len(pending)


def result_to_race_payload(result: dict) -> dict:
    """Build analyzable race structure from official result page."""
    finishers = result.get("finishers") or []
    meeting_date = result.get("meeting_date") or result.get("race_date") or ""
    venue_code = result.get("venue_code") or ""
    if not meeting_date or not venue_code:
        raise ValueError("missing meeting_date/race_date or venue_code in result payload")
    distance_m = int(result.get("distance_m") or 1200)
    dist_cat = distance_category(distance_m)
    meeting_id = meeting_id_from(meeting_date, venue_code)
    race_no = int(result["race_no"])
    race_id = f"{meeting_id}-r{race_no}"
    runners = []
    for f in finishers:
        horse_no = int(f.get("horse_no") or 0)
        odds = float(f.get("odds") or 10.0)
        draw = int(f.get("draw") or 0)
        placing = int(f.get("placing") or 9)
        stats = {
            "win_rate_10": 0.2 if placing == 1 else 0.1,
            "place_rate_10": 0.5 if placing <= 3 else 0.25,
            "distance_fit": 0.85,
            "track_fit": 0.85,
            "draw_fit": 0.8,
            "jockey_pair_rate": 0.15,
            "trainer_rate": 0.15,
        }
        runners.append({
            "horse_no": horse_no,
            "name": f.get("name") or "",
            "jockey": f.get("jockey") or "",
            "trainer": f.get("trainer") or "",
            "draw": draw,
            "weight": 0,
            "weight_delta": 0,
            "rating": 0,
            "age": 0,
            "sex": "",
            "recent_form": str(placing),
            "stats": stats,
            "odds": odds,
            "tags": [],
            "actual_placing": placing,
        })
    return {
        "id": race_id,
        "meeting_id": meeting_id,
        "race_no": race_no,
        "name": f"第{race_no}场",
        "distance_m": distance_m,
        "distance_category": dist_cat,
        "class": result.get("class") or "",
        "track_type": result.get("track_type") or "草地",
        "start_time": "",
        "prize_hkd": 0,
        "risk_level": "medium",
        "runners": runners,
        "winner_horse_no": result.get("winner_horse_no"),
    }
