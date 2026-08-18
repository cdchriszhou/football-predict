"""Canonical home/away repair must mirror match scores and related odds/predictions."""
import asyncio
import json
from types import SimpleNamespace

from data.match_status import (
    _apply_canonical_team_swap,
    _mirror_best_score_value,
    _mirror_score_odds_value,
    _mirror_score_token,
    _swap_match_results_for_side_swap,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, preds=None, odds=None):
        self.preds = preds or []
        self.odds = odds or []

    async def execute(self, stmt):
        sql = str(stmt)
        if "predictions" in sql:
            return _FakeResult(self.preds)
        if "odds" in sql:
            return _FakeResult(self.odds)
        return _FakeResult([])


def test_mirror_score_token():
    assert _mirror_score_token("2:1") == "1:2"
    assert _mirror_score_token("胜其它") == "胜其它"


def test_mirror_best_score_json():
    raw = '{"scores": ["2:1", "1:0"], "upset": "0:1"}'
    out = json.loads(_mirror_best_score_value(raw))
    assert out["scores"] == ["1:2", "0:1"]
    assert out["upset"] == "1:0"


def test_mirror_score_odds_crs_and_wdl():
    raw = {
        "2:0": 5.8,
        "0:2": 16.0,
        "胜其它": 150.0,
        "负其它": 300.0,
        "_meta": {
            "european": {"win_win": 1.79, "draw": 3.25, "win_lose": 3.8},
            "macau": {"handicap": "-1", "handicap_win": 4.02, "handicap_lose": 1.8},
        },
    }
    out = _mirror_score_odds_value(raw)
    assert out["0:2"] == 5.8
    assert out["2:0"] == 16.0
    assert out["负其它"] == 150.0
    assert out["胜其它"] == 300.0
    assert out["_meta"]["european"]["win_win"] == 3.8
    assert out["_meta"]["european"]["win_lose"] == 1.79
    assert out["_meta"]["macau"]["handicap"] == "+1"
    assert out["_meta"]["macau"]["handicap_win"] == 1.8


def test_swap_match_results():
    m = SimpleNamespace(result_a=1, result_b=0)
    _swap_match_results_for_side_swap(m)
    assert (m.result_a, m.result_b) == (0, 1)


def test_apply_canonical_team_swap_is_retired():
    match = SimpleNamespace(
        id=99,
        team_a="佛得角",
        team_b="乌拉圭",
        result_a=0,
        result_b=2,
        stage="小组赛",
    )
    db = _FakeSession()
    assert asyncio.run(_apply_canonical_team_swap(db, match)) is False
    assert (match.team_a, match.team_b) == ("佛得角", "乌拉圭")


def test_apply_canonical_team_swap_idempotent():
    match = SimpleNamespace(
        id=1,
        team_a="乌拉圭",
        team_b="佛得角",
        result_a=2,
        result_b=0,
        stage="小组赛",
    )
    db = _FakeSession()
    assert asyncio.run(_apply_canonical_team_swap(db, match)) is False
    assert (match.team_a, match.team_b) == ("乌拉圭", "佛得角")
    assert (match.result_a, match.result_b) == (2, 0)
