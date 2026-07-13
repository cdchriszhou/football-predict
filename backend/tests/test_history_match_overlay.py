"""History overlay supplements penalties and extra-time metadata."""
from datetime import datetime
from types import SimpleNamespace

from api.matches import match_to_dict
from data.match_status import history_match_overlay


def test_qf_extra_time_overlay_with_db_scores():
    m = SimpleNamespace(
        id=2104,
        competition_slug="worldcup-2026",
        stage="1/4决赛",
        group_name="",
        team_a="挪威",
        team_b="英格兰",
        match_time=datetime(2026, 7, 12, 5, 0),
        location="",
        stadium="",
        result_a=1,
        result_b=2,
        penalty_a=None,
        penalty_b=None,
        status="finished",
        season=None,
        matchday=None,
    )
    d = match_to_dict(m)
    assert d["extra_time"] is True
    assert d["regulation_a"] == 1 and d["regulation_b"] == 1


def test_r16_penalty_overlay_when_db_missing_pens():
    m = SimpleNamespace(
        id=2101,
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        group_name="",
        team_a="瑞士",
        team_b="哥伦比亚",
        match_time=datetime(2026, 7, 8, 1, 0),
        location="",
        stadium="",
        result_a=0,
        result_b=0,
        penalty_a=None,
        penalty_b=None,
        status="finished",
        season=None,
        matchday=None,
    )
    meta = history_match_overlay(m)
    assert meta["penalty_a"] == 4 and meta["penalty_b"] == 3
    d = match_to_dict(m)
    assert d["penalty_a"] == 4 and d["penalty_b"] == 3
