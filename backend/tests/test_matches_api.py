"""Tests for match API serialization."""
from datetime import datetime
from types import SimpleNamespace

from api.matches import match_to_dict
from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING


def _match(**kwargs):
    defaults = dict(
        id=1,
        competition_slug="premier-league",
        stage="第1轮",
        group_name="",
        team_a="利物浦",
        team_b="伯恩茅斯",
        match_time=datetime(2026, 8, 15, 19, 30),
        location="利物浦",
        stadium="安菲尔德",
        result_a=None,
        result_b=None,
        status=MATCH_UPCOMING,
        season=None,
        matchday=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_match_to_dict_exposes_live_scores():
    m = _match(status=MATCH_LIVE, result_a=1, result_b=0)
    data = match_to_dict(m)
    assert data["status"] == MATCH_LIVE
    assert data["result_a"] == 1
    assert data["result_b"] == 0


def test_match_to_dict_exposes_finished_scores():
    m = _match(status=MATCH_FINISHED, result_a=2, result_b=0)
    data = match_to_dict(m)
    assert data["status"] == MATCH_FINISHED
    assert data["result_a"] == 2
    assert data["result_b"] == 0


def test_match_to_dict_hides_missing_scores():
    m = _match(status=MATCH_UPCOMING, result_a=None, result_b=None)
    data = match_to_dict(m)
    assert data["result_a"] is None
    assert data["result_b"] is None
