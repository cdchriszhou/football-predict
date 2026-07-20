"""Prediction W/D/L, score, and reason consistency."""
from service.prediction_consistency import (
    build_repaired_view,
    sync_reason_with_view,
    wdl_score_mismatch,
    _strip_auto_notes,
)
from service.prediction_service import maybe_correct_odds_orientation, _implied_wdl
from utils.score_prediction import reconcile_prediction_view
from service.score_pick import dominant_wdl_outcome, _score_outcome


class _Pred:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Match:
    team_a = "新西兰"
    team_b = "埃及"


def test_sync_reason_replaces_auto_notes():
    raw = "DeepSeek分析埃及更强 | [热门比分] 1:0 / 2:0"
    view = reconcile_prediction_view(["0:1", "0:2"], "1:1", 66.8, 19.0, 14.2)
    out = sync_reason_with_view(raw, "新西兰", "埃及", view)
    assert "DeepSeek分析埃及更强" in out
    assert "1:0" not in out.split("[胜平负校正]")[-1]
    assert "[胜平负校正]" in out
    assert "埃及胜" in out
    assert "0:1" in out


def test_strip_auto_notes():
    assert _strip_auto_notes("a | [校验] x | [热门比分] 1:0") == "a"


def test_build_repaired_view_detects_mismatch():
    pred = _Pred(
        win_rate=66.8,
        draw_rate=19.0,
        lose_rate=14.2,
        best_score='{"scores": ["0:1", "0:2"], "upset": "1:1"}',
        reason="模型分析",
    )
    view, changed = build_repaired_view(pred, _Match())
    assert changed
    assert dominant_wdl_outcome(view["win_rate"], view["draw_rate"], view["lose_rate"]) == "lose"
    assert _score_outcome(view["best_scores"][0]) == "lose"


def test_maybe_correct_odds_orientation_swaps_rank_mismatch():
    odds = {
        "win_win": 1.42,
        "draw": 3.87,
        "win_lose": 6.0,
        "score_odds": {"1:0": 5.75, "0:1": 6.8},
    }
    fixed = maybe_correct_odds_orientation(odds, rank_a=89, rank_b=29)
    imp = _implied_wdl(fixed["win_win"], fixed["draw"], fixed["win_lose"])
    assert imp["imp_lose"] > imp["imp_win"]
    assert fixed["score_odds"]["0:1"] == 5.75
