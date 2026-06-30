"""
football-data.org v4 API client — real fixtures, standings, squads for五大联赛.

Docs: https://www.football-data.org/documentation/quickstart
Requires FOOTBALL_DATA_API_KEY (free tier: 10 req/min).
"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from utils.logger import logger

FD_BASE = "https://api.football-data.org/v4"
BEIJING = ZoneInfo("Asia/Shanghai")

_last_request = 0.0
_min_interval = 6.5  # free tier ~10/min


async def _rate_limit() -> None:
    global _last_request
    import time
    elapsed = time.monotonic() - _last_request
    if elapsed < _min_interval:
        await asyncio.sleep(_min_interval - elapsed)
    _last_request = time.monotonic()


def _api_key() -> str:
    from service.runtime_config import get_secret
    return get_secret("football_data_api_key").strip()


def _headers() -> dict[str, str]:
    key = _api_key()
    h = {"Accept": "application/json"}
    if key:
        h["X-Auth-Token"] = key
    return h


def _parse_dt(val: str | None) -> Optional[datetime]:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


async def _get(path: str, params: dict | None = None) -> dict | None:
    if not _api_key():
        logger.warning("football-data.org: FOOTBALL_DATA_API_KEY not configured")
        return None
    await _rate_limit()
    url = f"{FD_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=_headers(), params=params or {})
            if resp.status_code == 429:
                logger.warning("football-data.org rate limited, waiting 60s")
                await asyncio.sleep(60)
                resp = await client.get(url, headers=_headers(), params=params or {})
            if resp.status_code != 200:
                logger.warning(f"football-data.org HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()
    except Exception as e:
        logger.warning(f"football-data.org fetch failed: {e}")
        return None


def utc_to_beijing_naive(dt: datetime | None) -> datetime | None:
    """football-data utcDate → naive Beijing local (matches our schedule DB)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING).replace(tzinfo=None)


def extract_match_score(score: dict | None) -> tuple[int | None, int | None]:
    """Regulation/extra-time goals (excludes penalty shootout)."""
    parsed = extract_match_scores(score)
    return parsed["reg_a"], parsed["reg_b"]


def extract_match_scores(score: dict | None) -> dict:
    """Parse football-data score object into regulation + penalty shootout."""
    empty = {"reg_a": None, "reg_b": None, "pen_a": None, "pen_b": None}
    if not score:
        return empty

    def _block(block: dict | None) -> tuple[int | None, int | None]:
        if not block:
            return None, None
        home, away = block.get("home"), block.get("away")
        if home is not None and away is not None:
            return int(home), int(away)
        return None, None

    reg_a, reg_b = _block(score.get("fullTime"))
    if reg_a is None:
        reg_a, reg_b = _block(score.get("regularTime"))
    if reg_a is None:
        reg_a, reg_b = _block(score.get("halfTime"))

    pen_a, pen_b = _block(score.get("penalties"))

    return {"reg_a": reg_a, "reg_b": reg_b, "pen_a": pen_a, "pen_b": pen_b}


async def fetch_competition_matches(
    code: str,
    season: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
) -> list[dict]:
    """Return normalized match rows from /competitions/{code}/matches."""
    params: dict[str, Any] = {"season": season}
    if date_from:
        params["dateFrom"] = date_from.isoformat()
    if date_to:
        params["dateTo"] = date_to.isoformat()
    if status:
        params["status"] = status
    data = await _get(f"/competitions/{code}/matches", params)
    if not data:
        return []
    out: list[dict] = []
    for m in data.get("matches") or []:
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        score = m.get("score") or {}
        scores = extract_match_scores(score)
        ra, rb = scores["reg_a"], scores["reg_b"]
        pen_a, pen_b = scores["pen_a"], scores["pen_b"]
        kickoff_utc = _parse_dt(m.get("utcDate"))
        out.append({
            "external_id": m.get("id"),
            "matchday": m.get("matchday"),
            "season": str(m.get("season", {}).get("startDate", season))[:4] if m.get("season") else str(season),
            "utc_date": kickoff_utc,
            "kickoff_beijing": utc_to_beijing_naive(kickoff_utc),
            "status_raw": m.get("status"),
            "home_id": home.get("id"),
            "away_id": away.get("id"),
            "home_name_en": home.get("name") or home.get("shortName"),
            "away_name_en": away.get("name") or away.get("shortName"),
            "result_a": ra,
            "result_b": rb,
            "penalty_a": pen_a,
            "penalty_b": pen_b,
            "venue": (m.get("venue") or home.get("venue") or ""),
        })
    logger.info(f"football-data.org: {len(out)} matches for {code} season {season}")
    return out


async def fetch_standings(code: str, season: int) -> list[dict]:
    data = await _get(f"/competitions/{code}/standings", {"season": season})
    if not data:
        return []
    rows: list[dict] = []
    for block in data.get("standings") or []:
        if block.get("type") != "TOTAL":
            continue
        for entry in block.get("table") or []:
            team = entry.get("team") or {}
            rows.append({
                "fd_id": team.get("id"),
                "name_en": team.get("name") or team.get("shortName"),
                "rank": entry.get("position"),
                "points": entry.get("points"),
                "played": entry.get("playedGames"),
                "won": entry.get("won"),
                "draw": entry.get("draw"),
                "lost": entry.get("lost"),
                "goals_for": entry.get("goalsFor"),
                "goals_against": entry.get("goalsAgainst"),
            })
    logger.info(f"football-data.org: {len(rows)} standing rows for {code}")
    return rows


async def fetch_team_squad(team_id: int) -> dict | None:
    data = await _get(f"/teams/{team_id}")
    if not data:
        return None
    squad = []
    for p in data.get("squad") or []:
        squad.append({
            "name": p.get("name"),
            "name_en": p.get("name"),
            "position": p.get("position"),
            "nationality": p.get("nationality"),
            "date_of_birth": p.get("dateOfBirth"),
            "shirt_number": p.get("shirtNumber"),
        })
    return {
        "fd_id": data.get("id"),
        "name_en": data.get("name"),
        "short_name": data.get("shortName"),
        "venue": data.get("venue"),
        "squad": squad,
    }


def map_match_status(raw: str | None) -> str:
    from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING
    mapping = {
        "SCHEDULED": MATCH_UPCOMING,
        "TIMED": MATCH_UPCOMING,
        "IN_PLAY": MATCH_LIVE,
        "LIVE": MATCH_LIVE,
        "PAUSED": MATCH_LIVE,
        "FINISHED": MATCH_FINISHED,
        "POSTPONED": MATCH_UPCOMING,
        "SUSPENDED": MATCH_LIVE,
        "CANCELLED": MATCH_FINISHED,
        "AWARDED": MATCH_FINISHED,
    }
    return mapping.get(raw or "", MATCH_UPCOMING)


def map_player_position(raw: str | None) -> str:
    mapping = {
        "Goalkeeper": "GK",
        "Defence": "DF",
        "Defender": "DF",
        "Midfield": "MF",
        "Midfielder": "MF",
        "Offence": "FW",
        "Attacker": "FW",
        "Forward": "FW",
    }
    return mapping.get(raw or "", "MF")


def player_age_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        born = datetime.fromisoformat(dob.replace("Z", "+00:00")).date()
        today = datetime.now().date()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except ValueError:
        return None
