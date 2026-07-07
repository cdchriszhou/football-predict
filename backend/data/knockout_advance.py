"""Resolve knockout feeder slots (第N场胜者/负者) and advance teams in DB."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.worldcup_knockout_schedule import KNOCKOUT_FIXTURES
from db.models import Match

FEEDER_WIN = re.compile(r"^第(\d+)场胜者$")
FEEDER_LOSE = re.compile(r"^第(\d+)场负者$")

FIXTURE_BY_NO = {fx["match_no"]: fx for fx in KNOCKOUT_FIXTURES}

KICKOFF_TOLERANCE_SEC = 3600


def _parse_kickoff(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    return None


def _kickoff_delta(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    return abs((a - b).total_seconds())


def find_row_for_fixture(fx: dict, pool: list[Any], by_teams: dict[str, Any]) -> Any | None:
    """Map a FIFA fixture to a DB row (kickoff first, then template / team names)."""
    target = _parse_kickoff(fx.get("match_time"))
    best = None
    best_delta = KICKOFF_TOLERANCE_SEC + 1
    if target:
        for m in pool:
            mt = _parse_kickoff(_field(m, "match_time"))
            delta = _kickoff_delta(mt, target)
            if delta is not None and delta <= KICKOFF_TOLERANCE_SEC and delta < best_delta:
                best, best_delta = m, delta
    if best:
        return best

    for m in pool:
        if _field(m, "team_a") == fx["team_a"] and _field(m, "team_b") == fx["team_b"]:
            return m

    if not fx["team_a"].startswith("第") and not fx["team_b"].startswith("第"):
        return by_teams.get(_team_key(fx["team_a"], fx["team_b"]))

    # Partially advanced row: fixed seed team + feeder on the other slot.
    if not fx["team_a"].startswith("第"):
        for m in pool:
            if _field(m, "team_a") == fx["team_a"] and (
                _field(m, "team_b") == fx["team_b"] or str(_field(m, "team_b", "")).startswith("第")
            ):
                return m
    if not fx["team_b"].startswith("第"):
        for m in pool:
            if _field(m, "team_b") == fx["team_b"] and (
                _field(m, "team_a") == fx["team_a"] or str(_field(m, "team_a", "")).startswith("第")
            ):
                return m
    return None

# Same wing slot order as frontend BRACKET_LAYOUT (all match_nos per stage).
SLOT_ORDER: dict[str, list[int]] = {}
for side, layout in (
    ("left", {"1/16决赛": [74, 77, 73, 75, 83, 84, 81, 82], "1/8决赛": [89, 90, 93, 94],
              "1/4决赛": [97, 98], "半决赛": [101]}),
    ("right", {"1/16决赛": [76, 78, 79, 80, 85, 87, 88, 86], "1/8决赛": [91, 92, 96, 95],
               "1/4决赛": [99, 100], "半决赛": [102]}),
):
    for stage, nos in layout.items():
        SLOT_ORDER.setdefault(stage, []).extend(nos)
SLOT_ORDER["决赛"] = [104]
SLOT_ORDER["季军赛"] = [103]

CANONICAL_BY_STAGE: dict[str, list[int]] = {}
for fx in KNOCKOUT_FIXTURES:
    CANONICAL_BY_STAGE.setdefault(fx["stage"], []).append(fx["match_no"])
for stage in CANONICAL_BY_STAGE:
    CANONICAL_BY_STAGE[stage].sort()

KNOCKOUT_STAGES = sorted(CANONICAL_BY_STAGE.keys(), key=lambda s: CANONICAL_BY_STAGE[s][0])


async def ensure_knockout_fixtures(db: AsyncSession, slug: str = "worldcup-2026") -> int:
    """Insert missing knockout placeholder rows so bracket API never returns empty."""
    if slug != "worldcup-2026":
        return 0
    from data.worldcup_knockout_schedule import build_knockout_matches
    from data.status_constants import MATCH_UPCOMING

    expected = build_knockout_matches()
    existing = list((await db.execute(
        select(Match).where(
            Match.competition_slug == slug,
            Match.stage.in_(KNOCKOUT_STAGES),
        )
    )).scalars().all())

    if len(existing) >= len(expected):
        return 0

    window = timedelta(minutes=45)
    created = 0
    for item in expected:
        mt = item["match_time"]
        matched = any(
            m.stage == item["stage"]
            and m.match_time is not None
            and abs((m.match_time - mt).total_seconds()) <= window.total_seconds()
            for m in existing
        )
        if matched:
            continue
        row = Match(
            competition_slug=slug,
            stage=item["stage"],
            group_name=item.get("group_name", ""),
            team_a=item["team_a"],
            team_b=item["team_b"],
            match_time=item["match_time"],
            location=item.get("location", ""),
            stadium=item.get("stadium", ""),
            result_a=None,
            result_b=None,
            status=MATCH_UPCOMING,
        )
        db.add(row)
        existing.append(row)
        created += 1

    if created:
        from db.sqlite_write import flush_session
        await flush_session(db)
        invalidate_knockout_slot_index_cache(slug)
    return created


def _team_key(a: str, b: str) -> str:
    return "|".join(sorted([a, b]))


def parse_feeder(name: str) -> tuple[str, int] | tuple[str, None]:
    if not name:
        return ("team", None)
    m = FEEDER_WIN.match(name)
    if m:
        return ("winner", int(m.group(1)))
    m = FEEDER_LOSE.match(name)
    if m:
        return ("loser", int(m.group(1)))
    return ("team", None)


def match_winner(
    m: Any,
    *,
    match_no: int | None = None,
    by_no: dict[int, Any] | None = None,
) -> str | None:
    if m is None:
        return None
    ra = _field(m, "result_a")
    rb = _field(m, "result_b")
    if ra is None or rb is None:
        from data.match_status import confirmed_scores_from_history
        hist = confirmed_scores_from_history(m)
        if hist:
            ra, rb = hist["result_a"], hist["result_b"]
        else:
            return None
    ta = _field(m, "team_a")
    tb = _field(m, "team_b")
    if match_no and by_no:
        rta, rtb = resolve_fixture_teams(match_no, by_no)
        ta = rta or (ta if ta and not str(ta).startswith("第") else None)
        tb = rtb or (tb if tb and not str(tb).startswith("第") else None)
    elif (ta and str(ta).startswith("第")) or (tb and str(tb).startswith("第")):
        return None
    if not ta or not tb:
        return None
    if ra > rb:
        return ta
    if rb > ra:
        return tb
    pa = _field(m, "penalty_a")
    pb = _field(m, "penalty_b")
    if pa is not None and pb is not None:
        if pa > pb:
            return ta
        if pb > pa:
            return tb
    return None


def match_loser(
    m: Any,
    *,
    match_no: int | None = None,
    by_no: dict[int, Any] | None = None,
) -> str | None:
    w = match_winner(m, match_no=match_no, by_no=by_no)
    if not w or m is None:
        return None
    ta = _field(m, "team_a")
    tb = _field(m, "team_b")
    return tb if w == ta else ta


def _field(m: Any, name: str, default=None):
    if isinstance(m, dict):
        return m.get(name, default)
    return getattr(m, name, default)


def build_slot_index(stage_rows: dict[str, list[Any]]) -> dict[int, Any]:
    """Map FIFA match_no → API/DB row (same rules as frontend buildMatchIndex)."""
    seen: dict[str, Any] = {}
    for rows in (stage_rows or {}).values():
        for m in rows or []:
            stage = _field(m, "stage")
            ta = _field(m, "team_a")
            tb = _field(m, "team_b")
            key = f"{stage}|{ta}|{tb}"
            mid = _field(m, "id") or 0
            prev = seen.get(key)
            if not prev or mid > (_field(prev, "id") or 0):
                seen[key] = m

    by_teams: dict[str, Any] = {}
    for m in seen.values():
        ta = _field(m, "team_a")
        tb = _field(m, "team_b")
        k = _team_key(ta, tb)
        mid = _field(m, "id") or 0
        prev = by_teams.get(k)
        if not prev or mid > (_field(prev, "id") or 0):
            by_teams[k] = m

    by_no: dict[int, Any] = {}

    for stage, nos in SLOT_ORDER.items():
        pool = [seen[k] for k in seen if _field(seen[k], "stage") == stage]

        for no in nos:
            fx = FIXTURE_BY_NO.get(no)
            if not fx:
                continue
            hit = find_row_for_fixture(fx, pool, by_teams)
            if hit:
                by_no[no] = hit

    for stage, no in (("决赛", 104), ("季军赛", 103)):
        pool = [seen[k] for k in seen if _field(seen[k], "stage") == stage]
        if pool:
            by_no[no] = pool[0]

    return by_no


def resolve_feeder_team(name: str, by_no: dict[int, Any], cache: dict[str, str | None]) -> str | None:
    if not name:
        return None
    if name in cache:
        return cache[name]
    kind, ref_no = parse_feeder(name)
    if kind == "team":
        cache[name] = name if not name.startswith("第") else None
        return cache[name]
    feeder = by_no.get(ref_no or -1)
    if kind == "winner":
        out = match_winner(feeder, match_no=ref_no, by_no=by_no)
    else:
        out = match_loser(feeder, match_no=ref_no, by_no=by_no)
    cache[name] = out
    return out


def _desired_team(template: str, resolved: str | None, current: str | None) -> str:
    """Fixed seed stays; feeder slots use winner or official placeholder text."""
    if not template.startswith("第"):
        return template
    if resolved:
        return resolved
    return template


def resolve_fixture_teams(match_no: int, by_no: dict[int, Any]) -> tuple[str | None, str | None]:
    fx = FIXTURE_BY_NO.get(match_no)
    if not fx:
        return None, None
    cache: dict[str, str | None] = {}
    ta = resolve_feeder_team(fx["team_a"], by_no, cache)
    tb = resolve_feeder_team(fx["team_b"], by_no, cache)
    return ta, tb


async def load_knockout_slot_index(db: AsyncSession, slug: str = "worldcup-2026") -> dict[int, Any]:
    """Load all knockout rows and map FIFA match_no → DB row."""
    if slug != "worldcup-2026":
        return {}
    stages = sorted({fx["stage"] for fx in KNOCKOUT_FIXTURES}, key=lambda s: CANONICAL_BY_STAGE[s][0])
    stage_rows: dict[str, list[Match]] = {}
    for stage in stages:
        rows = list((await db.execute(
            select(Match).where(
                Match.competition_slug == slug,
                Match.stage == stage,
            ).order_by(Match.match_time.asc())
        )).scalars().all())
        stage_rows[stage] = rows
    return build_slot_index(stage_rows)


_ko_index_cache: dict[str, tuple[float, dict[int, Any]]] = {}
_KO_INDEX_TTL_SEC = 30


async def load_knockout_slot_index_cached(db: AsyncSession, slug: str = "worldcup-2026") -> dict[int, Any]:
    """Cached wrapper — dashboard hits this on every /today + /recent-results."""
    now = time.monotonic()
    cached = _ko_index_cache.get(slug)
    if cached and now - cached[0] < _KO_INDEX_TTL_SEC:
        return cached[1]
    index = await load_knockout_slot_index(db, slug)
    _ko_index_cache[slug] = (now, index)
    return index


def invalidate_knockout_slot_index_cache(slug: str = "worldcup-2026") -> None:
    _ko_index_cache.pop(slug, None)


def _clean_team_label(name: str | None) -> str:
    if not name or str(name).startswith("第"):
        return ""
    return str(name)


def display_teams_for_match(m: Match, by_no: dict[int, Any]) -> tuple[str, str]:
    """Resolve feeder placeholders to real team names for API display."""
    db_a = _clean_team_label(m.team_a)
    db_b = _clean_team_label(m.team_b)
    if db_a and db_b:
        return db_a, db_b

    if not by_no:
        return db_a, db_b

    match_no = None
    for no, row in by_no.items():
        if _field(row, "id") == m.id:
            match_no = no
            break
    if match_no is None:
        return _clean_team_label(m.team_a), _clean_team_label(m.team_b)

    fx = FIXTURE_BY_NO.get(match_no)
    if not fx:
        return _clean_team_label(m.team_a), _clean_team_label(m.team_b)

    resolved_a, resolved_b = resolve_fixture_teams(match_no, by_no)
    ta = fx["team_a"] if not fx["team_a"].startswith("第") else (resolved_a or "")
    tb = fx["team_b"] if not fx["team_b"].startswith("第") else (resolved_b or "")
    return ta, tb


async def advance_knockout_teams(
    db: AsyncSession,
    slug: str = "worldcup-2026",
    *,
    flush: bool = True,
) -> int:
    """Fill placeholder team names on later knockout rounds from finished feeders."""
    if slug != "worldcup-2026":
        return 0

    stages = sorted({fx["stage"] for fx in KNOCKOUT_FIXTURES}, key=lambda s: CANONICAL_BY_STAGE[s][0])
    stage_rows: dict[str, list[Match]] = {}
    for stage in stages:
        rows = list((await db.execute(
            select(Match).where(
                Match.competition_slug == slug,
                Match.stage == stage,
            ).order_by(Match.match_time.asc())
        )).scalars().all())
        stage_rows[stage] = rows

    by_no = build_slot_index(stage_rows)
    updated = 0

    for fx in sorted(KNOCKOUT_FIXTURES, key=lambda x: x["match_no"]):
        no = fx["match_no"]
        if not fx["team_a"].startswith("第") and not fx["team_b"].startswith("第"):
            continue
        row = by_no.get(no)
        if not row:
            continue
        resolved_a, resolved_b = resolve_fixture_teams(no, by_no)
        target_a = _desired_team(fx["team_a"], resolved_a, _field(row, "team_a"))
        target_b = _desired_team(fx["team_b"], resolved_b, _field(row, "team_b"))
        changed = False
        if _field(row, "team_a") != target_a:
            row.team_a = target_a
            changed = True
        if _field(row, "team_b") != target_b:
            row.team_b = target_b
            changed = True
        if changed:
            by_no[no] = row
            updated += 1

    if updated and flush:
        from db.sqlite_write import flush_session
        await flush_session(db)
        invalidate_knockout_slot_index_cache(slug)
    return updated
