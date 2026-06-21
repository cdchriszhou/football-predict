"""Tests for contextual score adjustments (odds + standings + knockout path)."""
from service.score_context import (
    apply_contextual_score_adjustments,
    enrich_knockout_outlook,
    market_score_profile,
)


def _crs(**kwargs):
    base = {
        "1:0": 6.5, "2:0": 8.0, "2:1": 7.5, "3:0": 12.0, "3:1": 14.0,
        "0:0": 9.0, "1:1": 6.0, "0:1": 7.0, "0:2": 11.0, "1:2": 10.0,
        "0:3": 18.0, "2:2": 16.0,
    }
    base.update(kwargs)
    return base


def test_market_profile_deep_favourite():
    prof = market_score_profile({
        "win_win": 1.35,
        "win_lose": 7.5,
        "draw": 4.5,
        "handicap": "-1",
        "handicap_win": 1.85,
        "handicap_lose": 1.95,
        "over_under": "2.5",
        "imp_win": 62.0,
        "imp_draw": 22.0,
        "imp_lose": 16.0,
    })
    assert prof["deep_fav"] is True
    assert prof["fav_a"] is True
    assert prof["cover_a"] is True


def test_collusion_draw_promotion():
    ctx = {
        "stage": "小组赛",
        "matchday": 3,
        "both_need_draw": True,
        "group_table": [],
    }
    best = apply_contextual_score_adjustments(
        ["2:1", "1:0"],
        _crs(),
        group_context=ctx,
        win_rate=34.0,
        lose_rate=32.0,
        draw_rate=34.0,
    )
    assert best[0] in ("1:1", "0:0")


def test_must_win_need_goals_aggressive():
    ctx = {
        "stage": "小组赛",
        "matchday": 3,
        "must_win_a": True,
        "need_goals_a": True,
        "group_rank_a": 3,
        "standing_a": {"team": "A", "played": 2, "points": 1, "goals_for": 1},
        "group_avg_gf": 1.35,
    }
    best = apply_contextual_score_adjustments(
        ["1:0", "1:1"],
        _crs(),
        group_context=ctx,
        win_rate=58.0,
        lose_rate=20.0,
        draw_rate=22.0,
    )
    assert best[0] in ("2:1", "3:1", "3:0")


def test_handicap_blowout_primary():
    odds = {
        "win_win": 1.28,
        "win_lose": 9.0,
        "draw": 5.5,
        "handicap": "-1.5",
        "handicap_win": 1.92,
        "handicap_lose": 1.88,
        "over_under": "3.0",
        "imp_win": 68.0,
        "imp_draw": 18.0,
        "imp_lose": 14.0,
    }
    best = apply_contextual_score_adjustments(
        ["1:0", "2:0"],
        _crs(),
        odds_dict=odds,
        win_rate=70.0,
        lose_rate=12.0,
        draw_rate=18.0,
        expected_a=2.3,
        expected_b=0.7,
    )
    try:
        ga, gb = map(int, best[0].split(":"))
    except ValueError:
        ga, gb = 0, 0
    assert ga > gb and ga + gb >= 3


def test_knockout_outlook_enrichment():
    ctx = {
        "stage": "小组赛",
        "matchday": 3,
        "group_name": "A",
        "group_table": [
            {"team": "墨西哥", "points": 6, "goals_for": 4, "goals_against": 1},
            {"team": "韩国", "points": 3, "goals_for": 2, "goals_against": 2},
        ],
        "standing_a": {"team": "墨西哥", "played": 2, "points": 6, "goals_for": 4, "goals_against": 1},
        "standing_b": {"team": "韩国", "played": 2, "points": 3, "goals_for": 2, "goals_against": 2},
        "must_win_b": True,
    }
    enrich_knockout_outlook(
        ctx, "墨西哥", "韩国", 14, 22,
        paired_group_ranks={"B": [12, 18, 35, 40]},
    )
    assert ctx.get("finish_band_a") == "leading"
    assert ctx.get("r16_opponent_rank_a") == 18
    assert ctx.get("path_pressure_b", 0) > 0
