"""Canonical Beijing kickoff times from FIFA group-stage schedule."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

# Verified venue-local → Beijing wall-clock (PT/ET afternoon slots span +1 Beijing day)
KICKOFF_OVERRIDES_BEIJING: dict[tuple[str, str], datetime] = {
    # Seattle 12:00 PT on 2026-06-19 → 2026-06-20 03:00 Beijing
    ("美国", "澳大利亚"): datetime(2026, 6, 20, 3, 0),
}


@lru_cache(maxsize=1)
def _schedule_by_teams() -> dict[tuple[str, str], datetime]:
    from crawler.schedule_crawler import _build_expected_matches
    from data.worldcup_knockout_schedule import knockout_kickoff_by_teams

    mapping = {
        (m["team_a"], m["team_b"]): m["match_time"]
        for m in _build_expected_matches()
    }
    mapping.update(knockout_kickoff_by_teams())
    return mapping


def canonical_kickoff_beijing(team_a: str, team_b: str) -> datetime | None:
    """Return official schedule kickoff (naive Beijing local) for a group fixture."""
    from data.worldcup_venues import canonical_team_order

    ca, cb = canonical_team_order(team_a, team_b)
    key = (ca, cb)
    if key in KICKOFF_OVERRIDES_BEIJING:
        return KICKOFF_OVERRIDES_BEIJING[key]
    return _schedule_by_teams().get(key)
