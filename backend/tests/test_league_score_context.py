"""League-scale rank, draw preservation, and table motivation."""
from service.league_rank import (
    GAP_CLEAR,
    GAP_LARGE,
    GAP_MISMATCH,
    MINNOW_RANK,
    is_minnow_rank,
    rank_gap,
    table_rank,
)
from service.match_context import analyze_match_context, build_group_context
from service.score_pipeline.base import ScorerInput
from service.score_pipeline.poisson_scorer import PoissonModelScorer


def test_table_rank_rejects_fifa_scale_and_missing():
    assert table_rank(None) is None
    assert table_rank(0) is None
    assert table_rank(50) is None
    assert table_rank(75) is None
    assert table_rank(1) == 1
    assert table_rank(20) == 20
    assert table_rank(18) == 18


def test_rank_gap_zero_when_either_missing():
    assert rank_gap(1, None) == 0
    assert rank_gap(50, 1) == 0
    assert rank_gap(1, 16) == 15
    assert rank_gap(3, 11) == 8
    assert is_minnow_rank(16) is True
    assert is_minnow_rank(12) is False
    assert GAP_CLEAR == 8
    assert GAP_LARGE == 12
    assert GAP_MISMATCH == 15
    assert MINNOW_RANK == 16


def _inp(**kwargs) -> ScorerInput:
    base = dict(
        score_odds={"2:0": 5.0, "1:0": 5.5, "1:1": 6.5, "0:0": 9.0, "3:0": 8.0},
        win_rate=62.0,
        draw_rate=22.0,
        lose_rate=16.0,
        expected_a=1.8,
        expected_b=0.9,
        sp_win=1.40,
        sp_draw=4.2,
        sp_lose=7.5,
        rank_a=1,
        rank_b=16,
    )
    base.update(kwargs)
    return ScorerInput(**base)


def test_preserve_top_draw_skips_deep_favourite():
    scorer = PoissonModelScorer()
    dist = {"3:0": 10.0, "2:0": 8.0, "1:1": 2.0}
    out = scorer._preserve_top_draw(dist, _inp(win_rate=65.0, sp_win=1.35, rank_a=1, rank_b=18))
    assert out["1:1"] == 2.0


def test_preserve_top_draw_lifts_balanced_match():
    scorer = PoissonModelScorer()
    dist = {"1:0": 10.0, "1:1": 4.0}
    out = scorer._preserve_top_draw(
        dist,
        _inp(win_rate=46.0, lose_rate=32.0, draw_rate=22.0, sp_win=2.10, rank_a=8, rank_b=10),
    )
    assert out["1:1"] == 7.0


def test_rout_boost_runs_for_league_table_mismatch():
    scorer = PoissonModelScorer()
    dist = {"3:0": 1.0, "2:0": 1.0, "1:1": 1.0}
    out = scorer._apply_rout_boost(
        dist,
        _inp(win_rate=62.0, sp_win=1.48, rank_a=1, rank_b=16),
    )
    assert out["3:0"] > dist["3:0"]


def test_title_six_pointer_sets_must_win():
    standings = {
        "巴萨": {"team": "巴萨", "rank": 1, "points": 70, "played": 32},
        "皇马": {"team": "皇马", "rank": 2, "points": 68, "played": 32},
        "_size": 20,
    }
    ctx = build_group_context(
        "第33轮", "", 33, "巴萨", "皇马", 1, 2,
        standings=standings, home_side_override="a",
    )
    assert ctx["both_must_win"] is True
    assert ctx["dead_rubber"] is False
    analysis = analyze_match_context(
        {"name": "巴萨", "rank": 1, "tactic": "传控"},
        {"name": "皇马", "rank": 2, "tactic": "传控"},
        ctx,
    )
    assert any("需抢分" in a or "六分" in a for a in analysis.alerts)
    assert analysis.draw_adjustment < 0


def test_relegation_scrap_sets_must_win():
    standings = {
        "莱万特": {"team": "莱万特", "rank": 18, "points": 28, "played": 31},
        "埃尔切": {"team": "埃尔切", "rank": 19, "points": 26, "played": 31},
        "_size": 20,
    }
    ctx = build_group_context(
        "第32轮", "", 32, "莱万特", "埃尔切", 18, 19,
        standings=standings, home_side_override="a",
    )
    assert ctx["must_win_a"] is True
    assert ctx["must_win_b"] is True


def test_late_midtable_is_dead_rubber():
    standings = {
        "贝蒂斯": {"team": "贝蒂斯", "rank": 9, "points": 48, "played": 35},
        "比利亚雷亚尔": {"team": "比利亚雷亚尔", "rank": 10, "points": 47, "played": 35},
        "_size": 20,
    }
    ctx = build_group_context(
        "第36轮", "", 36, "贝蒂斯", "比利亚雷亚尔", 9, 10,
        standings=standings, home_side_override="a",
    )
    assert ctx["dead_rubber"] is True
    analysis = analyze_match_context(
        {"name": "贝蒂斯", "rank": 9, "tactic": "传控"},
        {"name": "比利亚雷亚尔", "rank": 10, "tactic": "传控"},
        ctx,
    )
    assert analysis.draw_adjustment > 0
    assert any("无关痛痒" in a for a in analysis.alerts)


def test_early_season_skips_table_motivation():
    standings = {
        "巴萨": {"team": "巴萨", "rank": 1, "points": 9, "played": 3},
        "皇马": {"team": "皇马", "rank": 2, "points": 7, "played": 3},
        "_size": 20,
    }
    ctx = build_group_context(
        "第3轮", "", 3, "巴萨", "皇马", 1, 2,
        standings=standings, home_side_override="a",
    )
    assert ctx["both_must_win"] is False
    assert ctx["dead_rubber"] is False


def test_missing_rank_does_not_invent_fifa_gap():
    ctx = build_group_context(
        "第10轮", "", 10, "巴萨", "马拉加", None, 20,
        home_side_override="a",
    )
    assert ctx["rank_gap"] == 0
    analysis = analyze_match_context(
        {"name": "巴萨", "tactic": "传控"},
        {"name": "马拉加", "rank": 20, "tactic": "防反"},
        ctx,
    )
    assert analysis.upset_risk == 0
