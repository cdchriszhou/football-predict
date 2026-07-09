"""July 7 R16 history seeds for dashboard score overlay."""
from types import SimpleNamespace

from data.match_status import confirmed_scores_from_history
from data.worldcup_history import HISTORICAL_MATCHES


def _wc2026_key(team_a: str, team_b: str, stage: str) -> dict | None:
    for item in HISTORICAL_MATCHES:
        if item.get("year") != 2026:
            continue
        if item.get("team_a") == team_a and item.get("team_b") == team_b and item.get("stage") == stage:
            return item
    return None


def test_july7_r16_portugal_spain():
    row = _wc2026_key("葡萄牙", "西班牙", "1/8决赛")
    assert row is not None
    assert row["result_a"] == 0 and row["result_b"] == 1


def test_july7_r16_usa_belgium():
    row = _wc2026_key("美国", "比利时", "1/8决赛")
    assert row is not None
    assert row["result_a"] == 1 and row["result_b"] == 4


def test_history_overlay_knockout_placeholder():
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        team_a="第83场胜者",
        team_b="第84场胜者",
        match_time=__import__("datetime").datetime(2026, 7, 7, 2, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    hist = confirmed_scores_from_history(m)
    assert hist is not None
    assert hist["result_a"] == 0 and hist["result_b"] == 1


def test_july8_r16_argentina_egypt():
    row = _wc2026_key("阿根廷", "埃及", "1/8决赛")
    assert row is not None
    assert row["result_a"] == 3 and row["result_b"] == 2


def test_july8_r16_switzerland_colombia_penalties():
    row = _wc2026_key("瑞士", "哥伦比亚", "1/8决赛")
    assert row is not None
    assert row["result_a"] == 0 and row["result_b"] == 0
    assert row["penalty_a"] == 4 and row["penalty_b"] == 3


def test_july8_history_overlay_by_kickoff():
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        team_a="阿根廷",
        team_b="埃及",
        match_time=__import__("datetime").datetime(2026, 7, 8, 0, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    hist = confirmed_scores_from_history(m)
    assert hist is not None
    assert hist["result_a"] == 3 and hist["result_b"] == 2


def test_july8_penalty_winner_from_history():
    from data.knockout_advance import match_winner

    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        team_a="瑞士",
        team_b="哥伦比亚",
        match_time=__import__("datetime").datetime(2026, 7, 8, 1, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    assert match_winner(m) == "瑞士"
