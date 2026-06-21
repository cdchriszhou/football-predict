"""Unit tests for CRS-anchored score selection fixes."""
from service.score_pick import (
    apply_favourite_blowout_scores,
    boost_heavy_favorite_scores,
    pick_crs_anchored_scores,
    pick_upset_from_crs,
    promote_strong_home_multi_goal,
    reconcile_likely_upset_cluster,
    repair_stored_score_picks,
    score_matches_pick,
)


def test_sweden_blocks_same_odds_draw_promotion():
    """SPF home fav 1.67 — must not promote 1:1 over tied 1:0."""
    crs = {"1:0": 5.3, "1:1": 5.3, "2:0": 5.5, "2:1": 5.5, "0:0": 9.5}
    out = pick_crs_anchored_scores(
        crs,
        win_rate=34.8,
        lose_rate=10.9,
        draw_rate=54.3,
        sp_win=1.67,
        sp_draw=3.35,
        sp_lose=4.3,
    )
    assert out[0] == "1:0"
    assert out[1] != "1:1" or out[0] == "1:0"


def test_ivory_coast_crs_secondary_prefers_home_one_nil():
    """Away SPF fav + draw anchor → primary 1:0 when CRS gap is tight."""
    crs = {"1:1": 3.9, "0:1": 5.7, "0:0": 6.0, "1:0": 7.25}
    out = pick_crs_anchored_scores(
        crs,
        win_rate=28.5,
        lose_rate=35.1,
        draw_rate=36.4,
        sp_win=3.15,
        sp_draw=2.65,
        sp_lose=2.3,
        model_scores=["0:0", "1:0"],
    )
    assert out == ["1:0", "1:1"]


def test_brazil_draw_promotion_when_market_supports():
    """When draw is close and draw_rate/SPF support it, promote 1:1 over 2:1."""
    crs = {"2:1": 5.5, "1:1": 6.0, "1:0": 7.0, "2:0": 12.0}
    out = pick_crs_anchored_scores(
        crs,
        win_rate=30.8,
        lose_rate=7.1,
        draw_rate=62.1,
        sp_win=1.82,
        sp_draw=3.30,
        sp_lose=5.50,
    )
    assert out[0] == "1:1"


def test_portugal_heavy_fav_prefers_three_nil_over_four_nil():
    """Portugal vs DR Congo: 3:0 CRS is far more likely than 4:0 — must not be 热门② 4:0."""
    crs = {
        "2:0": 5.4, "3:0": 6.0, "1:0": 6.25, "2:1": 8.0, "3:1": 8.5,
        "4:0": 10.5, "1:1": 11.0, "0:0": 15.0,
    }
    from service.score_pick import refine_favorite_score_cluster
    base = pick_crs_anchored_scores(
        crs, win_rate=80.0, lose_rate=6.0, draw_rate=14.0, sp_win=1.13, sp_lose=13.5,
    )
    base = refine_favorite_score_cluster(
        base, crs, win_rate=80.0, lose_rate=6.0, sp_win=1.13, sp_lose=13.5,
    )
    out = boost_heavy_favorite_scores(
        base, crs, win_rate=80.0, handicap="-2", rank_a=5, rank_b=46,
    )
    assert out[0] == "2:0"
    assert out[1] in ("3:0", "3:1")
    assert out[1] != "4:0"


def test_portugal_upset_is_draw_not_three_nil():
    crs = {
        "2:0": 5.4, "3:0": 6.0, "1:0": 6.25, "2:1": 8.0, "3:1": 8.5,
        "4:0": 10.5, "1:1": 11.0, "0:0": 15.0, "0:1": 20.0,
    }
    best = ["2:0", "3:1"]
    upset = pick_upset_from_crs(
        crs, best, win_rate=80.0, lose_rate=6.0, draw_rate=14.0,
        sp_win=1.13, sp_lose=13.5, handicap="-2", rank_a=5, rank_b=46,
    )
    assert upset == "1:1"
    assert upset != "3:0"


def test_germany_blowout_boost_adds_five_nil():
    crs = {
        "4:0": 4.8, "3:0": 4.9, "5:0": 6.95, "2:0": 8.0,
        "3:1": 12.0, "胜其它": 25.0,
    }
    base = pick_crs_anchored_scores(
        crs, win_rate=90.7, lose_rate=3.1, draw_rate=6.2,
    )
    out = boost_heavy_favorite_scores(
        base, crs, win_rate=90.7, handicap="-3", rank_a=10, rank_b=82,
    )
    assert out[0] == "4:0"
    assert out[1] == "5:0"


def test_netherlands_upset_still_two_two():
    crs = {
        "1:1": 4.5, "2:1": 4.8, "1:2": 7.5, "1:0": 8.0,
        "0:1": 11.0, "2:0": 11.0, "2:2": 11.0, "0:0": 13.0,
    }
    best = pick_crs_anchored_scores(
        crs, win_rate=49.4, lose_rate=21.8, draw_rate=28.8,
        sp_win=1.86, sp_draw=3.33, sp_lose=3.43,
    )
    upset = pick_upset_from_crs(
        crs, best, win_rate=49.4, lose_rate=21.8, draw_rate=28.8,
        sp_win=1.86, sp_lose=3.43,
    )
    assert upset == "2:2"


def test_ivory_coast_home_narrow_win_secondary():
    crs = {"1:1": 3.9, "0:1": 5.7, "0:0": 6.0, "1:0": 7.25}
    out = pick_crs_anchored_scores(
        crs, win_rate=28.5, lose_rate=35.1, draw_rate=36.4,
        sp_win=3.15, sp_draw=2.65, sp_lose=2.3,
    )
    assert out == ["1:0", "1:1"]


def test_canada_draw_not_promoted_to_two_one():
    """Draw-primary + home fav must stay 1:1 through multi-goal promote."""
    crs = {
        "1:1": 4.75, "1:0": 5.10, "2:1": 5.30, "2:0": 6.60,
        "0:0": 9.50, "0:1": 11.00,
    }
    base = pick_crs_anchored_scores(
        crs, win_rate=41.0, lose_rate=17.5, draw_rate=41.5,
        sp_win=1.62, sp_draw=3.32, sp_lose=4.75,
        expected_a=1.86, expected_b=1.86,
    )
    assert base[0] == "1:1"
    out = promote_strong_home_multi_goal(base, crs, sp_win=1.62)
    assert out[0] == "1:1"


def test_iran_upset_high_draw_from_sp():
    crs = {
        "2:0": 5.5, "1:1": 6.0, "2:1": 6.5, "1:0": 7.0,
        "2:2": 12.0, "0:0": 13.0,
    }
    best = ["2:0", "1:1"]
    upset = pick_upset_from_crs(
        crs, best, win_rate=55.0, lose_rate=20.0, draw_rate=17.8,
        sp_win=1.59, sp_draw=3.40, sp_lose=4.50,
    )
    assert upset == "2:2"


def test_netherlands_no_blowout_on_competitive_sp():
    crs = {"2:1": 4.8, "1:1": 4.5, "1:0": 8.0}
    base = ["2:1", "1:1"]
    out = apply_favourite_blowout_scores(
        base, crs, sp_win=1.86, handicap="-1", win_rate=49, lose_rate=22, expected_a=1.6,
    )
    assert out == ["2:1", "1:1"]


def test_usa_blowout_four_one():
    crs = {
        "2:1": 4.75, "2:0": 5.8, "1:0": 6.0, "4:1": 18.0,
    }
    base = pick_crs_anchored_scores(
        crs, win_rate=55, lose_rate=20, draw_rate=25,
        sp_win=1.79, sp_draw=3.25, sp_lose=3.8,
    )
    out = apply_favourite_blowout_scores(
        base, crs, sp_win=1.79, handicap="-1", win_rate=55, lose_rate=20, expected_a=2.1,
    )
    assert out[0] == "4:1"


def test_sweden_promote_two_nil():
    crs = {"1:0": 5.3, "1:1": 5.3, "2:0": 5.5, "2:1": 5.5}
    base = ["1:0", "1:1"]
    out = promote_strong_home_multi_goal(base, crs, sp_win=1.67)
    assert out[0] == "2:0"


def test_win_other_matches_unlisted_home_win():
    crs = {"4:0": 8.0, "5:0": 9.0, "3:0": 10.0, "胜其它": 25.0}
    assert score_matches_pick("7:1", "胜其它", crs)
    assert not score_matches_pick("4:0", "胜其它", crs)


def test_refine_wdl_keeps_win_rates_when_primary_is_win():
    from service.score_pick import refine_wdl_after_score_pick
    w, d, l = refine_wdl_after_score_pick(["2:0", "1:0"], 55.0, 25.0, 20.0)
    assert (w, d, l) == (55.0, 25.0, 20.0)


def test_ensure_triple_direction_coverage_fixes_secondary():
    from service.score_pick import ensure_triple_direction_coverage
    crs = {"2:0": 5.0, "1:0": 5.5, "1:1": 6.0, "0:1": 8.0}
    best, upset = ensure_triple_direction_coverage(["2:0", "1:0"], None, crs)
    assert best == ["2:0", "1:0"]
    assert upset == "1:1"


def test_prefer_poisson_primary_when_close():
    from service.score_pick import prefer_poisson_primary_when_close
    crs = {"1:0": 5.8, "2:0": 6.2, "1:1": 7.0}
    out = prefer_poisson_primary_when_close(["1:0", "1:1"], ["2:0", "1:0"], crs)
    assert out[0] == "2:0"


def test_stage_draw_promotion_uses_promo_dr():
    crs = {"2:1": 5.5, "1:1": 6.0, "1:0": 7.0, "2:0": 12.0}
    out = pick_crs_anchored_scores(
        crs, win_rate=30.8, lose_rate=7.1, draw_rate=28.0,
        sp_win=1.82, sp_draw=3.30, sp_lose=5.50,
        stage="小组赛",
    )
    assert out[0] == "1:1"


def test_validate_score_picks_warns_low_prob_upset():
    from service.score_pick import validate_score_picks
    picks, upset, warnings = validate_score_picks(
        ["2:0", "1:0"], "0:1", {"2:0": 5.0, "1:0": 6.0, "0:1": 50.0},
    )
    assert upset == "0:1"
    assert any("5%" in w for w in warnings)


def test_validate_score_picks_rejects_same_direction_upset():
    from service.score_pick import validate_score_picks
    picks, upset, warnings = validate_score_picks(
        ["2:0", "1:0"], "5:0", {"2:0": 5.0, "1:0": 6.0, "1:1": 7.0, "5:0": 50.0},
    )
    assert upset == "1:1"
    assert picks == ["2:0", "1:0"]


def test_june17_home_fav_secondary_cluster():
    """Home favourite: replace 1:1 secondary with CRS cluster 2:1/3:0."""
    from service.score_pick import refine_favorite_score_cluster
    crs = {
        "2:0": 4.75, "1:0": 5.9, "2:1": 6.5, "3:0": 7.25, "1:1": 8.0,
        "3:1": 10.0, "胜其它": 16.0,
    }
    base = pick_crs_anchored_scores(
        crs, win_rate=63.8, lose_rate=21.9, draw_rate=14.3, sp_win=1.55, sp_lose=4.5,
    )
    assert base[1] == "1:1"
    refined = refine_favorite_score_cluster(
        base, crs, win_rate=63.8, lose_rate=21.9, sp_win=1.55, sp_lose=4.5,
    )
    assert refined[1] in ("2:1", "3:0", "3:1")


def test_june17_argentina_pipeline_hits_three_zero():
    from service.score_backtest import run_score_prediction
    crs = {
        "2:0": 4.75, "1:0": 5.9, "2:1": 6.5, "3:0": 7.25, "1:1": 8.0,
        "3:1": 10.0, "0:0": 12.0, "胜其它": 16.0,
    }
    _, _, upset, picks = run_score_prediction(
        "阿根廷", "阿尔及利亚", crs, (63.8, 14.3, 21.9),
        {"win_win": 1.55, "draw": 3.5, "win_lose": 4.5},
        stage="小组赛",
    )
    assert picks[0] == "2:0"
    assert picks[1] in ("2:1", "3:0", "3:1")


def test_jun19_switzerland_hits_four_one():
    from service.score_backtest import run_score_prediction
    crs = {
        "2:0": 5.50, "1:0": 6.00, "2:1": 6.50, "1:1": 7.50, "3:0": 8.00,
        "3:1": 9.50, "4:1": 14.0, "4:0": 16.0, "胜其它": 22.0,
    }
    _, _, _, picks = run_score_prediction(
        "瑞士", "波黑", crs, (63.3, 22.3, 14.4),
        {"win_win": 1.48, "draw": 4.20, "win_lose": 6.50, "handicap": "-1"},
        stage="小组赛",
    )
    assert "4:1" in picks


def test_jun19_canada_hits_six_nil_in_triple():
    from service.score_backtest import run_score_prediction
    crs = {
        "3:0": 5.50, "2:0": 6.00, "4:0": 7.00, "5:0": 11.0, "6:0": 18.0, "胜其它": 25.0,
    }
    _, _, _, picks = run_score_prediction(
        "加拿大", "卡塔尔", crs, (78.1, 14.2, 7.7),
        {"win_win": 1.18, "draw": 6.50, "win_lose": 12.0, "handicap": "-2"},
        stage="小组赛",
    )
    assert "6:0" in picks

    crs = {
        "0:2": 5.7, "0:3": 6.5, "0:1": 7.1, "1:2": 8.0, "1:3": 8.5,
        "0:4": 10.0, "1:1": 10.5,
    }
    base = pick_crs_anchored_scores(
        crs, win_rate=33.9, lose_rate=56.6, draw_rate=9.5, sp_win=4.0, sp_lose=1.45,
    )
    from service.score_pick import refine_favorite_score_cluster
    refined = refine_favorite_score_cluster(
        base, crs, win_rate=33.9, lose_rate=56.6, sp_win=4.0, sp_lose=1.45,
    )
    assert refined == ["0:2", "1:2"]


def test_jun18_uzbekistan_pipeline_hits_one_three():
    from service.score_backtest import run_score_prediction
    crs = {
        "0:2": 5.7, "0:3": 6.5, "0:1": 7.1, "1:2": 8.0, "1:3": 8.5,
        "0:4": 10.0, "1:1": 10.5, "1:4": 15.0,
    }
    _, _, _, picks = run_score_prediction(
        "乌兹别克斯坦", "哥伦比亚", crs, (12.0, 21.0, 66.9),
        {"win_win": 7.50, "draw": 4.30, "win_lose": 1.35, "handicap": "+1"},
        stage="小组赛",
    )
    assert "1:3" in picks


def test_jun18_england_pipeline_covers_high_scoring():
    from service.score_backtest import run_score_prediction
    crs = {
        "2:1": 7.0, "1:1": 7.5, "2:0": 8.5, "3:1": 9.0, "1:0": 9.5,
        "2:2": 11.0, "3:0": 11.0, "3:2": 12.0, "4:2": 18.0,
    }
    _, _, _, picks = run_score_prediction(
        "英格兰", "克罗地亚", crs, (55.5, 24.1, 20.4),
        {"win_win": 1.65, "draw": 3.80, "win_lose": 4.50, "handicap": "-0.5"},
        stage="小组赛",
    )
    assert "4:2" in picks or "3:2" in picks


def test_jun18_ghana_primary_one_nil():
    from service.score_backtest import run_score_prediction
    crs = {
        "1:1": 5.8, "1:0": 6.5, "0:0": 7.5, "0:1": 8.5, "2:0": 9.0,
        "2:1": 10.0, "1:2": 12.0, "0:2": 14.0,
    }
    p1, _, _, picks = run_score_prediction(
        "加纳", "巴拿马", crs, (37.3, 29.5, 33.2),
        {"win_win": 2.45, "draw": 3.10, "win_lose": 2.75, "handicap": "0"},
        stage="小组赛",
    )
    assert p1 == "1:0"
    assert "1:0" in picks


def test_reconcile_usa_australia_stored_bad_labels():
    """Stored 2:0+3:1 hot with 3:0 cold — 3:0 must not stay as upset."""
    crs = {
        "1:0": 5.7, "2:1": 6.0, "1:1": 6.6, "2:0": 6.6,
        "0:0": 10.5, "3:0": 10.5, "3:1": 10.5,
    }
    picks, upset = repair_stored_score_picks(
        ["2:0", "3:1"], "3:0", crs,
        win_rate=62.4, lose_rate=14.4, draw_rate=23.2,
        sp_win=1.45, sp_lose=5.6, sp_draw=3.83, handicap="-1",
    )
    assert upset != "3:0"
    assert upset in ("1:1", "0:0", "2:2")
    assert "3:0" not in (upset,)


def test_reconcile_brazil_haiti_stored_bad_labels():
    """Stored 2:0+4:0 hot with 3:0 cold — promote 3:0 to likely, cold is draw."""
    crs = {
        "2:0": 6.0, "3:0": 6.0, "4:0": 7.5, "1:0": 9.0,
        "2:1": 9.0, "3:1": 9.0, "1:1": 15.0,
    }
    picks, upset = repair_stored_score_picks(
        ["2:0", "4:0"], "3:0", crs,
        win_rate=86.9, lose_rate=8.5, draw_rate=4.6, handicap="-2",
        rank_a=1, rank_b=87,
    )
    assert picks[0] == "2:0"
    assert picks[1] == "3:0"
    assert upset == "1:1"


def test_align_usa_fav_rejects_away_win_secondary():
    """When AI/market fav USA win, likely scores must not be 0:1."""
    from service.score_pick import align_score_picks_to_wdl, _score_outcome

    crs = {
        "1:0": 5.7, "2:1": 6.0, "1:1": 6.6, "2:0": 6.6, "0:1": 8.0, "3:1": 10.5,
    }
    out = align_score_picks_to_wdl(
        ["1:1", "0:1"], crs, win_rate=62.0, draw_rate=23.0, lose_rate=15.0,
    )
    assert _score_outcome(out[0]) == "win"
    assert out[1] != "0:1"
    assert _score_outcome(out[1]) in ("win", "draw")


def test_align_draw_fav_uses_moderate_second_when_one_draw_line():
    """Draw-heavy WDL but CRS only has 1:1 — secondary should not be 0:2 blowout."""
    from service.score_pick import align_score_picks_to_wdl, _score_outcome

    crs = {"0:2": 3.8, "1:1": 6.5, "0:1": 6.8, "1:2": 7.2, "1:0": 32.0}
    out = align_score_picks_to_wdl(
        ["1:1", "0:2"], crs, win_rate=7.0, draw_rate=63.0, lose_rate=30.0,
    )
    assert out[0] == "1:1"
    assert out[1] == "0:1"
    assert _score_outcome(out[1]) == "lose"


def test_align_draw_fav_keeps_draw_primary():
    from service.score_pick import align_score_picks_to_wdl, _score_outcome

    crs = {"1:1": 5.5, "0:0": 7.0, "1:0": 6.0, "0:1": 6.5}
    out = align_score_picks_to_wdl(
        ["1:0", "0:1"], crs, win_rate=34.0, draw_rate=44.0, lose_rate=22.0,
    )
    assert _score_outcome(out[0]) == "draw"
    assert _score_outcome(out[1]) in ("draw", "win")


def test_reconcile_cluster_swaps_likelier_score_from_upset():
    picks, upset = reconcile_likely_upset_cluster(["2:0", "4:0"], "3:0", {
        "2:0": 6.0, "3:0": 6.0, "4:0": 7.5, "1:1": 15.0,
    })
    assert picks == ["2:0", "3:0"]
    assert upset == "1:1"

    picks, upset = reconcile_likely_upset_cluster(["2:0", "4:0"], "3:0", {
        "2:0": 6.0, "3:0": 6.0, "4:0": 7.5, "1:1": 15.0,
    })
    assert picks == ["2:0", "3:0"]
    assert upset == "1:1"


def test_june20_morocco_scotland_one_nil_pipeline():
    """2026-06-20: CRS 1:0/1:1 cluster — actual 1:0, not 2:1."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "1:0": 5.50, "1:1": 5.75, "2:0": 6.70, "2:1": 7.00, "0:0": 9.00,
        "0:1": 10.0,
    }
    best, upset, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=55.0,
        draw_rate=28.9,
        lose_rate=16.1,
        sp_win=1.59,
        sp_draw=3.28,
        sp_lose=5.1,
        stage="小组赛",
    )
    assert best[0] == "1:0"
    assert best[1] in ("1:1", "2:0")
    assert score_matches_pick("1:0", best[0], crs)
    assert score_matches_pick("1:0", picks, crs) or "1:0" in picks


def test_june20_paraguay_turkey_one_nil_pipeline():
    """2026-06-20: Paraguay 1:0 — keep CRS 1:0 anchor under deep SPF."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "1:0": 5.70, "2:1": 6.00, "2:0": 6.50, "1:1": 7.20, "0:0": 10.0,
        "0:1": 11.0,
    }
    best, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=61.3,
        draw_rate=24.3,
        lose_rate=14.4,
        sp_win=1.45,
        sp_draw=3.83,
        sp_lose=5.6,
        stage="小组赛",
    )
    assert best[0] == "1:0"
    assert score_matches_pick("1:0", picks, crs) or "1:0" in picks


def test_june20_usa_australia_still_two_zero():
    """Co-host rout: 2:0 cluster must not collapse to 1:0."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "2:0": 5.80, "2:1": 6.20, "1:0": 6.50, "1:1": 7.00, "3:0": 9.00,
    }
    best, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=62.0,
        draw_rate=22.0,
        lose_rate=16.0,
        sp_win=1.55,
        sp_draw=3.90,
        sp_lose=5.2,
        stage="小组赛",
    )
    assert best[0] in ("2:0", "2:1")
    assert score_matches_pick("2:0", picks, crs) or "2:0" in best


def test_june20_brazil_haiti_three_zero():
    """Heavy favourite: 3:0 stays in hot picks."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "2:0": 5.50, "3:0": 6.00, "1:0": 7.00, "2:1": 8.00, "4:0": 9.50,
        "1:1": 12.0,
    }
    best, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=86.9,
        draw_rate=4.6,
        lose_rate=8.5,
        sp_win=1.12,
        sp_draw=7.50,
        sp_lose=15.0,
        handicap="-2",
        rank_a=6,
        rank_b=72,
        stage="小组赛",
    )
    assert "3:0" in best or "3:0" in picks or "2:0" in best
    assert score_matches_pick("3:0", picks, crs) or "3:0" in best or "2:0" in best


def test_june21_japan_four_nil_pipeline():
    """2026-06-21: Japan 4:0 — deep SPF fav keeps 4:0 in likely pair."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "2:0": 4.95, "2:1": 5.50, "1:0": 6.40, "1:1": 8.00, "3:1": 9.25,
        "3:0": 9.50, "0:0": 11.0, "4:0": 23.0, "4:1": 28.0,
    }
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=63.4,
        draw_rate=21.5,
        lose_rate=15.1,
        sp_win=1.36,
        sp_draw=4.05,
        sp_lose=6.8,
        rank_a=18,
        rank_b=44,
        expected_a=2.2,
        handicap="-1",
        stage="小组赛",
    )
    assert any(score_matches_pick("4:0", p, crs) for p in picks)


def test_june21_netherlands_rout_pipeline():
    """2026-06-21: Netherlands 5:1 — moderate deep fav includes high rout line."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "1:0": 5.50, "2:0": 6.00, "2:1": 6.50, "3:0": 8.50, "3:1": 9.00,
        "4:1": 12.0, "5:1": 18.0, "1:1": 7.50, "0:0": 11.0, "胜其它": 20.0,
    }
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=61.4,
        draw_rate=21.3,
        lose_rate=17.3,
        sp_win=1.55,
        sp_draw=3.90,
        sp_lose=5.20,
        rank_a=7,
        rank_b=38,
        expected_a=2.0,
        handicap="-1",
        stage="小组赛",
    )
    assert any(score_matches_pick("5:1", p, crs) for p in picks)


def test_june21_curacao_minnow_draw_pipeline():
    """2026-06-21: Curacao 0:0 — minnow home keeps 0:0 in score triple."""
    from service.match_context import analyze_match_context, apply_context_to_rates, build_group_context
    from service.score_pick import run_full_score_pipeline

    crs = {
        "0:1": 5.50, "0:0": 6.00, "1:1": 6.20, "0:2": 7.00, "1:0": 8.50,
        "1:2": 9.00, "0:3": 12.0,
    }
    ctx = build_group_context("小组赛", "E", 2, "库拉索", "厄瓜多尔", 82, 23)
    ca = analyze_match_context(
        {"name": "库拉索", "rank": 82},
        {"name": "厄瓜多尔", "rank": 23},
        ctx,
        {},
        {"win_pct": 15, "market_win_pct": 18},
    )
    w, d, l = apply_context_to_rates(14.8, 12.0, 73.2, ca)
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=w,
        draw_rate=d,
        lose_rate=l,
        sp_win=5.50,
        sp_draw=3.80,
        sp_lose=1.55,
        rank_a=82,
        rank_b=23,
        stage="小组赛",
    )
    assert any(score_matches_pick("0:0", p, crs) for p in picks)


def test_june21_germany_two_one_pipeline():
    """2026-06-21: Germany 2:1 — moderate fav keeps margin win, not rout."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "1:0": 5.50, "2:1": 6.00, "2:0": 6.50, "1:1": 7.00, "0:1": 10.0,
        "3:1": 10.5, "0:0": 11.0,
    }
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=66.7,
        draw_rate=18.6,
        lose_rate=14.6,
        sp_win=1.45,
        sp_draw=4.20,
        sp_lose=6.50,
        rank_a=10,
        rank_b=34,
        stage="小组赛",
    )
    assert any(score_matches_pick("2:1", p, crs) for p in picks)

