"""Canonical English status codes for matches and players."""

from __future__ import annotations

# Match lifecycle
MATCH_UPCOMING = "upcoming"
MATCH_LIVE = "live"
MATCH_FINISHED = "finished"

MATCH_LEGACY_MAP = {
    "未开始": MATCH_UPCOMING,
    "进行中": MATCH_LIVE,
    "已结束": MATCH_FINISHED,
}

ACTIVE_MATCH_STATUSES = (MATCH_UPCOMING, MATCH_LIVE)
FINISHED_MATCH_STATUSES = (MATCH_FINISHED,)

# Player availability
PLAYER_ACTIVE = "active"
PLAYER_MINOR_INJURY = "minor_injury"
PLAYER_INJURED = "injured"
PLAYER_SUSPENDED = "suspended"

PLAYER_LEGACY_MAP = {
    "正常": PLAYER_ACTIVE,
    "轻伤": PLAYER_MINOR_INJURY,
    "重伤": PLAYER_INJURED,
    "停赛": PLAYER_SUSPENDED,
}


def normalize_match_status(raw: str | None) -> str:
    if not raw:
        return MATCH_UPCOMING
    if raw in (MATCH_UPCOMING, MATCH_LIVE, MATCH_FINISHED):
        return raw
    return MATCH_LEGACY_MAP.get(raw, MATCH_UPCOMING)


def normalize_player_status(raw: str | None) -> str:
    if not raw:
        return PLAYER_ACTIVE
    if raw in (PLAYER_ACTIVE, PLAYER_MINOR_INJURY, PLAYER_INJURED, PLAYER_SUSPENDED):
        return raw
    return PLAYER_LEGACY_MAP.get(raw, PLAYER_ACTIVE)


def match_status_in_db_values(*canonical: str) -> tuple[str, ...]:
    """Expand canonical statuses to include legacy Chinese values for SQL IN clauses."""
    out: set[str] = set()
    reverse = {v: k for k, v in MATCH_LEGACY_MAP.items()}
    for s in canonical:
        out.add(s)
        if s in reverse:
            out.add(reverse[s])
    return tuple(out)
