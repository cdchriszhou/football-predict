"""Final and third-place history overlays for dashboard / bracket."""
from datetime import datetime
from types import SimpleNamespace

from api.matches import match_to_dict
from data.knockout_advance import build_slot_index, match_loser, match_winner, resolve_fixture_teams
from data.match_status import confirmed_scores_from_history
from data.worldcup_history import HISTORICAL_MATCHES


def _wc2026(team_a: str, team_b: str, stage: str) -> dict | None:
    for item in HISTORICAL_MATCHES:
        if item.get("year") != 2026:
            continue
        if item.get("team_a") == team_a and item.get("team_b") == team_b and item.get("stage") == stage:
            return item
    return None


def test_third_place_history():
    row = _wc2026("法国", "英格兰", "季军赛")
    assert row is not None
    assert row["result_a"] == 4 and row["result_b"] == 6


def test_final_history_spain_argentina_aet():
    row = _wc2026("西班牙", "阿根廷", "决赛")
    assert row is not None
    assert row["result_a"] == 1 and row["result_b"] == 0
    assert row["extra_time"] is True
    assert row["regulation_a"] == 0 and row["regulation_b"] == 0


def test_history_overlay_third_place_placeholder():
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="季军赛",
        team_a="第101场负者",
        team_b="第102场负者",
        match_time=datetime(2026, 7, 19, 5, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    hist = confirmed_scores_from_history(m)
    assert hist is not None
    assert hist["result_a"] == 4 and hist["result_b"] == 6


def test_history_overlay_final_placeholder():
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="决赛",
        team_a="第101场胜者",
        team_b="第102场胜者",
        match_time=datetime(2026, 7, 20, 3, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    hist = confirmed_scores_from_history(m)
    assert hist is not None
    assert hist["result_a"] == 1 and hist["result_b"] == 0
    assert hist["extra_time"] is True
    assert hist["regulation_a"] == 0 and hist["regulation_b"] == 0


def test_match_to_dict_overlays_final_score():
    m = SimpleNamespace(
        id=2104,
        competition_slug="worldcup-2026",
        stage="决赛",
        group_name="",
        team_a="第101场胜者",
        team_b="第102场胜者",
        match_time=datetime(2026, 7, 20, 3, 0),
        location="纽约/新泽西",
        stadium="大都会人寿体育场",
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
        status="finished",
        season=None,
        matchday=None,
    )
    d = match_to_dict(m)
    assert d["result_a"] == 1 and d["result_b"] == 0
    assert d["extra_time"] is True
    assert d["regulation_a"] == 0 and d["regulation_b"] == 0


def test_final_feeders_from_finished_semis():
    rows = {
        "半决赛": [
            {"id": 101, "stage": "半决赛", "team_a": "法国", "team_b": "西班牙",
             "result_a": 0, "result_b": 2, "match_time": "2026-07-15T02:00:00"},
            {"id": 102, "stage": "半决赛", "team_a": "英格兰", "team_b": "阿根廷",
             "result_a": 1, "result_b": 2, "match_time": "2026-07-16T03:00:00"},
        ],
        "季军赛": [
            {"id": 103, "stage": "季军赛", "team_a": "第101场负者", "team_b": "第102场负者",
             "match_time": "2026-07-19T05:00:00"},
        ],
        "决赛": [
            {"id": 104, "stage": "决赛", "team_a": "第101场胜者", "team_b": "第102场胜者",
             "match_time": "2026-07-20T03:00:00"},
        ],
    }
    by_no = build_slot_index(rows)
    assert match_winner(by_no[101], match_no=101, by_no=by_no) == "西班牙"
    assert match_loser(by_no[101], match_no=101, by_no=by_no) == "法国"
    assert match_winner(by_no[102], match_no=102, by_no=by_no) == "阿根廷"
    assert match_loser(by_no[102], match_no=102, by_no=by_no) == "英格兰"
    ta, tb = resolve_fixture_teams(103, by_no)
    assert ta == "法国" and tb == "英格兰"
    ta, tb = resolve_fixture_teams(104, by_no)
    assert ta == "西班牙" and tb == "阿根廷"
