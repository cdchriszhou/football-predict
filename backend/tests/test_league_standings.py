"""Tests for league standings computation."""
from data.league_standings import _Row, _apply_result


def test_apply_result_win():
    row = _Row()
    _apply_result(row, 2, 1)
    assert row.played == 1
    assert row.won == 1
    assert row.points == 3
    assert row.goal_diff == 1


def test_apply_result_draw():
    row = _Row()
    _apply_result(row, 1, 1)
    assert row.draw == 1
    assert row.points == 1


def test_apply_result_loss():
    row = _Row()
    _apply_result(row, 0, 2)
    assert row.lost == 1
    assert row.points == 0
    assert row.goal_diff == -2


def test_season_points_total():
    row = _Row()
    _apply_result(row, 2, 0)
    _apply_result(row, 1, 1)
    _apply_result(row, 0, 1)
    assert row.played == 3
    assert row.won == 1
    assert row.draw == 1
    assert row.lost == 1
    assert row.points == 4
    assert row.goals_for == 3
    assert row.goals_against == 2
