"""Tests for match API serialization."""
from datetime import datetime
from types import SimpleNamespace

from api.matches import match_to_dict
from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING


def _match(**kwargs):
    defaults = dict(
        id=1,
        competition_slug="worldcup-2026",
        stage="小组赛",
        group_name="A",
        team_a="墨西哥",
        team_b="南非",
        match_time=datetime(2026, 6, 12, 3, 0),
        location="墨西哥城",
        stadium="阿兹特克体育场",
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
