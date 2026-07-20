"""Schedule kickoff and today-match filtering."""
from datetime import datetime
from types import SimpleNamespace

from crawler.schedule_crawler import _build_expected_matches
from data.match_status import include_in_today_dashboard, resolve_public_match_status
from data.status_constants import MATCH_UPCOMING
from data.worldcup_schedule_lookup import canonical_kickoff_beijing
from utils.datetime_helpers import format_beijing_iso


def test_usa_australia_kickoff_beijing_june_20_0300():
    """Seattle 12:00 PT (Jun 19) = Beijing Jun 20 03:00 — not Jun 19 noon."""
    kt = canonical_kickoff_beijing("美国", "澳大利亚")
    assert kt == datetime(2026, 6, 20, 3, 0)
    built = next(
        m for m in _build_expected_matches()
        if m["team_a"] == "美国" and m["team_b"] == "澳大利亚"
    )
    assert built["match_time"] == datetime(2026, 6, 20, 3, 0)


def test_format_beijing_iso_appends_offset():
    assert format_beijing_iso(datetime(2026, 6, 20, 3, 0)) == "2026-06-20T03:00:00+08:00"


def test_today_dashboard_excludes_upcoming_kickoff():
    """Pre-kickoff fixtures belong in upcoming, not today's live/finished section."""
    m = SimpleNamespace(
        status=MATCH_UPCOMING,
        result_a=None,
        result_b=None,
        match_time=datetime(2026, 6, 20, 3, 0),
    )
    assert resolve_public_match_status(m) == MATCH_UPCOMING
    assert include_in_today_dashboard(m) is False


def test_today_dashboard_includes_finished():
    m = SimpleNamespace(
        status=MATCH_UPCOMING,
        result_a=2,
        result_b=1,
        match_time=datetime(2026, 6, 19, 3, 0),
    )
    assert resolve_public_match_status(m) == "finished"
    assert include_in_today_dashboard(m) is True


def test_usa_aus_wrong_db_time_still_treated_as_upcoming():
    """Crawler wrote noon Beijing on Jun 19; canonical is Jun 20 03:00."""
    m = SimpleNamespace(
        status=MATCH_UPCOMING,
        result_a=None,
        result_b=None,
        match_time=datetime(2026, 6, 19, 12, 0),
        team_a="美国",
        team_b="澳大利亚",
        competition_slug="worldcup-2026",
    )
    assert resolve_public_match_status(m) == MATCH_UPCOMING
    assert include_in_today_dashboard(m) is False


def test_usa_aus_wrong_finished_flag_excluded_from_today():
    """DB wrongly marked finished with no score and wrong kickoff day."""
    m = SimpleNamespace(
        status="finished",
        result_a=None,
        result_b=None,
        match_time=datetime(2026, 6, 19, 12, 0),
        team_a="美国",
        team_b="澳大利亚",
        competition_slug="worldcup-2026",
    )
    assert resolve_public_match_status(m) == MATCH_UPCOMING
    assert include_in_today_dashboard(m) is False


def test_group_d_matchday2_same_kickoff_both_fixtures():
    """USA-AUS and Paraguay-Turkey share Beijing 03:00 — both must exist in schedule."""
    built = _build_expected_matches()
    usa = next(m for m in built if m["team_a"] == "美国" and m["team_b"] == "澳大利亚")
    pry = next(m for m in built if m["team_a"] == "巴拉圭" and m["team_b"] == "土耳其")
    assert usa["match_time"] == datetime(2026, 6, 20, 3, 0)
    assert pry["match_time"] == datetime(2026, 6, 20, 3, 0)
    assert usa["group_name"] == "D" == pry["group_name"]
