"""History score overlay for dashboard read path."""
from datetime import datetime
from types import SimpleNamespace

from data.match_status import confirmed_scores_from_history


def test_history_overlay_r16_brazil_norway():
    m = SimpleNamespace(
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        team_a="巴西",
        team_b="挪威",
        match_time=datetime(2026, 7, 6, 4, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
    )
    hist = confirmed_scores_from_history(m)
    assert hist is not None
    assert hist["result_a"] == 1 and hist["result_b"] == 2
