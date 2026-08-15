"""Big-five leagues must be on 2026/27 season windows."""
from datetime import datetime

from data.competition_status import compute_season_status
from data.competitions import COMPETITIONS, get_competition


CLUB_SLUGS = (
    "premier-league",
    "la-liga",
    "serie-a",
    "bundesliga",
    "ligue-1",
)


def test_world_cup_removed_from_registry():
    assert "worldcup-2026" not in COMPETITIONS
    assert get_competition("worldcup-2026") is None


def test_big_five_season_year_is_2026():
    for slug in CLUB_SLUGS:
        assert get_competition(slug)["season_year"] == 2026


def test_big_five_opening_dates_are_august_2026():
    for slug in CLUB_SLUGS:
        opening = get_competition(slug)["opening_date"]
        assert opening.startswith("2026-08-"), slug


def test_big_five_closing_dates_are_2027():
    for slug in CLUB_SLUGS:
        closing = get_competition(slug)["closing_date"]
        assert closing.startswith("2027-"), slug


def test_mid_august_2026_status_before_most_kickoffs():
    """On 15 Aug morning UTC, only La Liga may be imminent; others upcoming."""
    now = datetime(2026, 8, 15, 8, 0, 0)
    assert compute_season_status(COMPETITIONS["premier-league"], {}, now) == "upcoming"
    assert compute_season_status(COMPETITIONS["serie-a"], {}, now) == "upcoming"
    assert compute_season_status(COMPETITIONS["bundesliga"], {}, now) == "upcoming"
    assert compute_season_status(COMPETITIONS["ligue-1"], {}, now) == "upcoming"
    assert compute_season_status(COMPETITIONS["la-liga"], {}, now) == "upcoming"


def test_after_premier_opening_is_live():
    now = datetime(2026, 8, 22, 0, 0, 0)
    assert compute_season_status(COMPETITIONS["premier-league"], {}, now) == "live"
    assert compute_season_status(COMPETITIONS["bundesliga"], {}, now) == "upcoming"
