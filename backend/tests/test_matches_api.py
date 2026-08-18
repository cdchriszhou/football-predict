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


def test_pick_latest_finished_matchday_keeps_whole_round():
    from api.matches import pick_latest_finished_matchday

    saturday = _match(
        id=1, team_a="阿拉维斯", team_b="赫塔费",
        match_time=datetime(2026, 8, 15, 23, 30),
        status=MATCH_FINISHED, result_a=3, result_b=0, matchday=1,
    )
    sunday = _match(
        id=2, team_a="西班牙人", team_b="莱万特",
        match_time=datetime(2026, 8, 16, 23, 0),
        status=MATCH_FINISHED, result_a=3, result_b=0, matchday=1,
    )
    monday_md2 = _match(
        id=3, team_a="巴塞罗那", team_b="马洛卡",
        match_time=datetime(2026, 8, 22, 3, 0),
        status=MATCH_FINISHED, result_a=2, result_b=1, matchday=2, stage="第2轮",
    )
    picked = pick_latest_finished_matchday([saturday, sunday])
    assert {m.id for m in picked} == {1, 2}

    picked_latest = pick_latest_finished_matchday([saturday, sunday, monday_md2])
    assert {m.id for m in picked_latest} == {3}
