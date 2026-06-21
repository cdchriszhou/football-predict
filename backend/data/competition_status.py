"""Derive competition season status for UI badges."""
from __future__ import annotations

from datetime import datetime, timezone


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def compute_season_status(comp: dict, stats: dict, now: datetime | None = None) -> str:
    """
    Return one of: upcoming | live | ended

    Priority: configured opening/closing dates, then match DB stats.
    """
    now = now or datetime.utcnow()
    opening = _parse_iso(comp.get("opening_date"))
    closing = _parse_iso(comp.get("closing_date"))

    if opening and now < opening:
        return "upcoming"
    if closing and now > closing:
        return "ended"

    matches = int(stats.get("matches") or 0)
    upcoming = int(stats.get("upcoming") or 0)
    live = int(stats.get("live") or 0)
    finished = int(stats.get("finished") or 0)

    if matches > 0:
        if live > 0:
            return "live"
        if upcoming > 0:
            return "live"
        if finished >= matches:
            return "ended"

    if opening and now >= opening:
        return "live"
    if comp.get("type") == "club" and not opening and not closing:
        return "live"
    if comp.get("type") == "racing" and opening and now >= opening:
        return "live"
    return "upcoming"
