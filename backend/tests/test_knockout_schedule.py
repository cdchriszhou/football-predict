"""Knockout bracket schedule and today-dashboard coverage."""
from datetime import datetime

from crawler.schedule_crawler import _build_all_expected_matches
from data.worldcup_knockout_schedule import KNOCKOUT_FIXTURES
from data.match_status import include_in_today_dashboard
from types import SimpleNamespace


def test_knockout_fixture_counts():
    all_matches = _build_all_expected_matches()
    assert len(all_matches) == 104
    r32 = [m for m in all_matches if m["stage"] == "1/16决赛"]
    assert len(r32) == 16
    assert len(KNOCKOUT_FIXTURES) == 32


def test_today_dashboard_includes_knockout_on_beijing_day(monkeypatch):
    """Brazil vs Japan R32 falls on 2026-06-30 Beijing calendar."""
    from datetime import date

    monkeypatch.setattr(
        "utils.datetime_helpers.china_today",
        lambda: date(2026, 6, 30),
    )
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/16决赛",
        group_name="",
        team_a="巴西",
        team_b="日本",
        match_time=datetime(2026, 6, 30, 1, 0),
        result_a=None,
        result_b=None,
        status="upcoming",
    )
    assert include_in_today_dashboard(m) is True
