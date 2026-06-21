"""Tests for World Cup group standings and tournament form."""
from datetime import datetime

from data.worldcup_group_standings import (
    GroupTeamStanding,
    apply_form_to_expected_goals,
    compute_standings_from_rows,
    load_standings_from_history,
    rank_standings,
)
from service.match_context import build_group_context, analyze_match_context


def _finished(team_a, team_b, ra, rb, group="J", t="2026-06-17T09:00:00"):
    return {
        "stage": "小组赛",
        "group_name": group,
        "team_a": team_a,
        "team_b": team_b,
        "result_a": ra,
        "result_b": rb,
        "match_time": t,
    }


def test_compute_standings_from_rows():
    rows = [
        _finished("阿根廷", "阿尔及利亚", 3, 0, t="2026-06-17T09:00:00"),
        _finished("奥地利", "约旦", 3, 1, t="2026-06-17T12:00:00"),
    ]
    st = compute_standings_from_rows(rows, "J")
    assert st["阿根廷"].points == 3
    assert st["阿根廷"].goals_for == 3
    assert st["约旦"].points == 0
    assert st["约旦"].lost == 1


def test_standings_respect_before_time():
    rows = [
        _finished("阿根廷", "阿尔及利亚", 3, 0, t="2026-06-17T09:00:00"),
        _finished("奥地利", "约旦", 3, 1, t="2026-06-18T12:00:00"),
    ]
    cutoff = datetime.fromisoformat("2026-06-18T00:00:00")
    st = compute_standings_from_rows(rows, "J", before_time=cutoff)
    assert "阿根廷" in st
    assert "奥地利" not in st


def test_rank_standings_by_points_and_gd():
    st = {
        "A": GroupTeamStanding("A", played=1, won=1, goals_for=2, goals_against=0),
        "B": GroupTeamStanding("B", played=1, won=1, goals_for=3, goals_against=1),
    }
    ranked = rank_standings(st)
    assert ranked[0].team == "B"


def test_must_win_after_zero_points_round2():
    rows = [_finished("英格兰", "塞尔维亚", 0, 1, group="C", t="2026-06-15T12:00:00")]
    st = compute_standings_from_rows(rows, "C")
    ctx = build_group_context(
        "小组赛", "C", 2, "英格兰", "丹麦",
        4, 20, standings=st,
    )
    assert ctx["must_win_a"] is True
    assert ctx["standing_a"]["points"] == 0


def test_qualified_after_round1_win():
    rows = [_finished("法国", "塞内加尔", 3, 1, group="I")]
    st = compute_standings_from_rows(rows, "I")
    ctx = build_group_context(
        "小组赛", "I", 2, "法国", "伊拉克",
        5, 58, standings=st,
    )
    assert ctx["qualified_a"] is True
    assert ctx["form_xg_a"] > 0


def test_apply_form_boosts_high_scorer():
    sa = GroupTeamStanding("A", played=1, won=1, goals_for=4, goals_against=0)
    sb = GroupTeamStanding("B", played=1, won=0, lost=1, goals_for=0, goals_against=1)
    ea, eb = apply_form_to_expected_goals(1.2, 1.0, sa, sb, 1.35, matchday=2)
    assert ea > 1.2
    assert eb <= 1.0


def test_analyze_match_context_alerts_must_win():
    ctx = build_group_context(
        "小组赛", "C", 2, "英格兰", "丹麦", 4, 20,
        standings=compute_standings_from_rows(
            [_finished("英格兰", "塞尔维亚", 0, 1, group="C")], "C",
        ),
    )
    analysis = analyze_match_context(
        {"name": "英格兰", "rank": 4},
        {"name": "丹麦", "rank": 20},
        ctx,
    )
    assert any("抢分" in a for a in analysis.alerts)


def test_load_standings_from_history_j_group():
    from data.worldcup_history import HISTORICAL_MATCHES
    hist = [m for m in HISTORICAL_MATCHES if m.get("year") == 2026 and m.get("group_name") == "J"]
    cutoff = datetime.fromisoformat("2026-06-18T00:00:00")
    st = load_standings_from_history(hist, "J", before_time=cutoff)
    assert st["阿根廷"].points == 3
    assert st["阿尔及利亚"].points == 0
