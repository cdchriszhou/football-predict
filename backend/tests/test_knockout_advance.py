"""Knockout bracket team advancement from feeder results."""
from data.knockout_advance import (
    build_slot_index,
    match_winner,
    resolve_fixture_teams,
)


def _m(ta, tb, ra, rb, pa=None, pb=None):
    return {
        "stage": "1/16决赛",
        "team_a": ta,
        "team_b": tb,
        "result_a": ra,
        "result_b": rb,
        "penalty_a": pa,
        "penalty_b": pb,
        "match_time": "2026-06-30",
        "id": 1,
    }


def test_resolve_r16_from_finished_r32():
    stage_rows = {
        "1/16决赛": [
            _m("德国", "巴拉圭", 1, 1, 4, 5),
            _m("法国", "瑞典", 2, 0),
            _m("巴西", "日本", 2, 1),
            _m("荷兰", "摩洛哥", 1, 1, 3, 4),
        ],
        "1/8决赛": [
            {
                "stage": "1/8决赛",
                "team_a": "第74场胜者",
                "team_b": "第77场胜者",
                "match_time": "2026-07-05",
                "id": 10,
            },
            {
                "stage": "1/8决赛",
                "team_a": "加拿大",
                "team_b": "第75场胜者",
                "match_time": "2026-07-05",
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
