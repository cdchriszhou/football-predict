"""July 10–12 quarter-finals must feed semi-final bracket slots."""
from datetime import datetime
from types import SimpleNamespace

from api.matches import match_to_dict
from data.knockout_advance import build_slot_index, match_winner, resolve_fixture_teams
from data.match_status import confirmed_scores_from_history
from data.worldcup_history import HISTORICAL_MATCHES


def _wc2026(team_a: str, team_b: str, stage: str) -> dict | None:
    for item in HISTORICAL_MATCHES:
        if item.get("year") != 2026:
            continue
        if item.get("team_a") == team_a and item.get("team_b") == team_b and item.get("stage") == stage:
            return item
    return None


def test_qf_france_morocco_history():
    row = _wc2026("法国", "摩洛哥", "1/4决赛")
    assert row is not None
    assert row["result_a"] == 2 and row["result_b"] == 0


def test_qf_spain_belgium_history():
    row = _wc2026("西班牙", "比利时", "1/4决赛")
    assert row is not None
    assert row["result_a"] == 2 and row["result_b"] == 1


def test_qf_argentina_switzerland_history():
    row = _wc2026("阿根廷", "瑞士", "1/4决赛")
    assert row is not None
    assert row["result_a"] == 3 and row["result_b"] == 1


def test_history_overlay_qf_placeholder():
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/4决赛",
        team_a="第95场胜者",
        team_b="第96场胜者",
        match_time=datetime(2026, 7, 12, 8, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    hist = confirmed_scores_from_history(m)
    assert hist is not None
    assert hist["result_a"] == 3 and hist["result_b"] == 1


def test_semi_feeders_from_finished_qf():
    rows = {
        "1/8决赛": [
            {"id": 89, "stage": "1/8决赛", "team_a": "巴拉圭", "team_b": "法国",
             "result_a": 0, "result_b": 1, "match_time": "2026-07-05T05:00:00"},
            {"id": 90, "stage": "1/8决赛", "team_a": "加拿大", "team_b": "摩洛哥",
             "result_a": 0, "result_b": 3, "match_time": "2026-07-05T00:00:00"},
            {"id": 93, "stage": "1/8决赛", "team_a": "葡萄牙", "team_b": "西班牙",
             "result_a": 0, "result_b": 1, "match_time": "2026-07-07T02:00:00"},
            {"id": 94, "stage": "1/8决赛", "team_a": "美国", "team_b": "比利时",
             "result_a": 1, "result_b": 4, "match_time": "2026-07-07T05:00:00"},
            {"id": 91, "stage": "1/8决赛", "team_a": "巴西", "team_b": "挪威",
             "result_a": 1, "result_b": 2, "match_time": "2026-07-06T04:00:00"},
            {"id": 92, "stage": "1/8决赛", "team_a": "墨西哥", "team_b": "英格兰",
             "result_a": 2, "result_b": 3, "match_time": "2026-07-06T08:00:00"},
            {"id": 95, "stage": "1/8决赛", "team_a": "阿根廷", "team_b": "埃及",
             "result_a": 3, "result_b": 2, "match_time": "2026-07-08T00:00:00"},
            {"id": 96, "stage": "1/8决赛", "team_a": "瑞士", "team_b": "哥伦比亚",
             "result_a": 0, "result_b": 0, "penalty_a": 4, "penalty_b": 3,
             "match_time": "2026-07-08T01:00:00"},
        ],
        "1/4决赛": [
            {"id": 97, "stage": "1/4决赛", "team_a": "第89场胜者", "team_b": "第90场胜者",
             "result_a": 2, "result_b": 0, "match_time": "2026-07-10T04:00:00"},
            {"id": 98, "stage": "1/4决赛", "team_a": "第93场胜者", "team_b": "第94场胜者",
             "result_a": 2, "result_b": 1, "match_time": "2026-07-11T00:00:00"},
            {"id": 99, "stage": "1/4决赛", "team_a": "第91场胜者", "team_b": "第92场胜者",
             "result_a": 1, "result_b": 2, "match_time": "2026-07-12T05:00:00"},
            {"id": 100, "stage": "1/4决赛", "team_a": "第95场胜者", "team_b": "第96场胜者",
             "result_a": 3, "result_b": 1, "match_time": "2026-07-12T08:00:00"},
        ],
        "半决赛": [
            {"id": 101, "stage": "半决赛", "team_a": "第97场胜者", "team_b": "第98场胜者",
             "match_time": "2026-07-15T02:00:00"},
            {"id": 102, "stage": "半决赛", "team_a": "第99场胜者", "team_b": "第100场胜者",
             "match_time": "2026-07-16T03:00:00"},
        ],
    }
    by_no = build_slot_index(rows)
    assert match_winner(by_no[97], match_no=97, by_no=by_no) == "法国"
    assert match_winner(by_no[98], match_no=98, by_no=by_no) == "西班牙"
    assert match_winner(by_no[100], match_no=100, by_no=by_no) == "阿根廷"
    ta, tb = resolve_fixture_teams(101, by_no)
    assert ta == "法国" and tb == "西班牙"
    ta, tb = resolve_fixture_teams(102, by_no)
    assert ta == "英格兰" and tb == "阿根廷"


def test_match_to_dict_overlays_qf_score():
    m = SimpleNamespace(
        id=2105,
        competition_slug="worldcup-2026",
        stage="1/4决赛",
        group_name="",
        team_a="阿根廷",
        team_b="瑞士",
        match_time=datetime(2026, 7, 12, 8, 0),
        location="堪萨斯城",
        stadium="",
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
        status="finished",
        season=None,
        matchday=None,
    )
    d = match_to_dict(m)
    assert d["result_a"] == 3 and d["result_b"] == 1
    assert d["extra_time"] is True
    assert d["regulation_a"] == 1 and d["regulation_b"] == 1


def test_history_overlay_penalties_on_draw_without_db_pens():
    from data.match_status import history_match_overlay

    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        team_a="瑞士",
        team_b="哥伦比亚",
        match_time=datetime(2026, 7, 8, 1, 0),
        result_a=0,
        result_b=0,
        penalty_a=None,
        penalty_b=None,
    )
    meta = history_match_overlay(m)
    assert meta["penalty_a"] == 4 and meta["penalty_b"] == 3
