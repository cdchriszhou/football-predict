"""Knockout bracket team advancement from feeder results."""
from types import SimpleNamespace

from data.knockout_advance import (
    build_slot_index,
    display_teams_for_match,
    materialize_knockout_slot_index,
    match_winner,
    resolve_fixture_teams,
)


def _m(ta, tb, ra, rb, pa=None, pb=None, mid=1):
    return {
        "stage": "1/16决赛",
        "team_a": ta,
        "team_b": tb,
        "result_a": ra,
        "result_b": rb,
        "penalty_a": pa,
        "penalty_b": pb,
        "match_time": "2026-06-30",
        "id": mid,
    }


def test_display_teams_for_knockout_slot():
    r32_a = SimpleNamespace(
        id=1, stage="1/16决赛", team_a="巴西", team_b="日本",
        result_a=2, result_b=1, penalty_a=None, penalty_b=None, match_time="2026-06-30T01:00:00",
    )
    r16 = SimpleNamespace(
        id=10, stage="1/8决赛", team_a="第76场胜者", team_b="第78场胜者",
        result_a=None, result_b=None, penalty_a=None, penalty_b=None,
        match_time="2026-07-06T04:00:00",
    )
    by_no = build_slot_index({"1/16决赛": [r32_a], "1/8决赛": [r16]})
    m = SimpleNamespace(id=10, team_a="第76场胜者", team_b="第78场胜者", competition_slug="worldcup-2026")
    ta, tb = display_teams_for_match(m, by_no)
    assert ta == "巴西"
    assert tb == ""


def test_resolve_r16_from_finished_r32():
    stage_rows = {
        "1/16决赛": [
            _m("德国", "巴拉圭", 1, 1, 4, 5, 1),
            _m("法国", "瑞典", 2, 0, mid=2),
            _m("巴西", "日本", 2, 1, mid=3),
            _m("荷兰", "摩洛哥", 1, 1, 3, 4, mid=4),
        ],
        "1/8决赛": [
            {
                "stage": "1/8决赛",
                "team_a": "第74场胜者",
                "team_b": "第77场胜者",
                "match_time": "2026-07-05T05:00:00",
                "id": 10,
            },
            {
                "stage": "1/8决赛",
                "team_a": "加拿大",
                "team_b": "第75场胜者",
                "match_time": "2026-07-05T00:00:00",
                "id": 11,
            },
        ],
    }
    by_no = build_slot_index(stage_rows)
    assert match_winner(by_no[74]) == "巴拉圭"
    assert match_winner(by_no[77]) == "法国"
    assert match_winner(by_no[76]) == "巴西"
    assert match_winner(by_no[75]) == "摩洛哥"

    ta, tb = resolve_fixture_teams(89, by_no)
    assert ta == "巴拉圭"
    assert tb == "法国"

    ta, tb = resolve_fixture_teams(90, by_no)
    assert ta == "加拿大"
    assert tb == "摩洛哥"

    ta, tb = resolve_fixture_teams(91, by_no)
    assert ta == "巴西"


def test_display_teams_resolves_via_kickoff_and_history():
    """Dashboard may return QF rows whose id is absent from the slot index."""
    from datetime import datetime

    r16 = {
        89: {
            "id": 201, "stage": "1/8决赛", "team_a": "法国", "team_b": "巴拉圭",
            "result_a": 1, "result_b": 0, "penalty_a": None, "penalty_b": None,
            "match_time": datetime(2026, 7, 5, 5, 0),
        },
        90: {
            "id": 202, "stage": "1/8决赛", "team_a": "加拿大", "team_b": "摩洛哥",
            "result_a": 0, "result_b": 3, "penalty_a": None, "penalty_b": None,
            "match_time": datetime(2026, 7, 5, 0, 0),
        },
    }
    # Finished QF still has feeder placeholders; id not present in by_no.
    qf = SimpleNamespace(
        id=9999,
        stage="1/4决赛",
        team_a="第89场胜者",
        team_b="第90场胜者",
        match_time=datetime(2026, 7, 10, 4, 0),
        competition_slug="worldcup-2026",
        result_a=2,
        result_b=0,
        penalty_a=None,
        penalty_b=None,
    )
    ta, tb = display_teams_for_match(qf, r16)
    assert ta == "法国"
    assert tb == "摩洛哥"


def test_display_teams_history_fallback_when_feeders_missing():
    from datetime import datetime

    qf = SimpleNamespace(
        id=8888,
        stage="1/4决赛",
        team_a="第93场胜者",
        team_b="第94场胜者",
        match_time=datetime(2026, 7, 11, 0, 0),
        competition_slug="worldcup-2026",
        result_a=2,
        result_b=1,
        penalty_a=None,
        penalty_b=None,
    )
    ta, tb = display_teams_for_match(qf, {})
    assert ta == "西班牙"
    assert tb == "比利时"


def test_materialize_knockout_slot_index_produces_dicts():
    row = {
        "id": 77, "stage": "1/16决赛", "team_a": "法国", "team_b": "瑞典",
        "result_a": 3, "result_b": 0, "penalty_a": None, "penalty_b": None,
        "match_time": "2026-07-01T06:00:00", "competition_slug": "worldcup-2026",
        "group_name": "", "location": "", "stadium": "", "status": "finished",
        "season": None, "matchday": None,
    }
    idx = materialize_knockout_slot_index({77: row})
    assert isinstance(idx[77], dict)
    assert idx[77]["team_a"] == "法国"
    # display_teams must not touch SQLAlchemy when fed materialized rows
    m = SimpleNamespace(id=77, team_a="法国", team_b="瑞典", competition_slug="worldcup-2026")
    ta, tb = display_teams_for_match(m, idx)
    assert ta == "法国" and tb == "瑞典"
