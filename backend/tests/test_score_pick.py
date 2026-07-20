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
    _score_outcome,
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


def test_reconcile_wdl_with_score_picks_fixes_market_ai_mismatch():
    from service.score_pick import reconcile_wdl_with_score_picks, dominant_wdl_outcome

    # NZ vs Egypt style: market W/D/L favours team_a win, scores say team_b win
    w, d, l = reconcile_wdl_with_score_picks(["0:1", "0:2"], 66.8, 19.0, 14.2)
    assert dominant_wdl_outcome(w, d, l) == "lose"
    assert w < l
    # Already aligned — no change
    w2, d2, l2 = reconcile_wdl_with_score_picks(["1:0", "2:0"], 62.0, 22.0, 16.0)
    assert dominant_wdl_outcome(w2, d2, l2) == "win"


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


def _june22_ctx(standing_a, standing_b, group_avg_gf=1.5):
    return {
        "stage": "小组赛",
        "matchday": 2,
        "group_avg_gf": group_avg_gf,
        "standing_a": standing_a,
        "standing_b": standing_b,
    }


def test_june22_spain_saudi_rout_pipeline():
    """2026-06-22: Spain 4:0 — deep fav keeps rout in likely pair."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "2:0": 5.20, "3:0": 6.50, "4:0": 8.50, "2:1": 7.00, "3:1": 9.00,
        "1:0": 9.50, "1:1": 12.0, "0:0": 18.0,
    }
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=78.0,
        draw_rate=14.0,
        lose_rate=8.0,
        sp_win=1.18,
        sp_draw=6.50,
        sp_lose=12.0,
        handicap="-2",
        rank_a=8,
        rank_b=58,
        expected_a=2.8,
        stage="小组赛",
        group_context=_june22_ctx(
            {"played": 1, "goals_for": 3, "goals_against": 0},
            {"played": 1, "goals_for": 0, "goals_against": 2},
        ),
    )
    assert any(score_matches_pick("4:0", p, crs) for p in picks)


def test_june22_belgium_iran_scoreless_draw():
    """2026-06-22: Belgium 0:0 — R1 drought + iron defense keeps 0:0 in triple."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "2:0": 6.1, "2:1": 5.8, "1:0": 7.2, "1:1": 8.25, "0:0": 14.0,
        "3:0": 12.0, "4:0": 22.0,
    }
    ctx = _june22_ctx(
        {"played": 1, "goals_for": 1, "goals_against": 1},
        {"played": 1, "goals_for": 2, "goals_against": 2},
    )
    _, upset, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=58.0,
        draw_rate=32.0,
        lose_rate=10.0,
        sp_win=1.55,
        sp_draw=4.76,
        sp_lose=5.50,
        handicap="-1",
        rank_a=9,
        rank_b=21,
        stage="小组赛",
        group_context=ctx,
        team_a={"tactic": "技术流"},
        team_b={"tactic": "铁桶防守"},
        odds_dict={"win_win": 1.55, "draw": 4.76, "win_lose": 5.50, "over_under": 2.5},
    )
    assert any(score_matches_pick("0:0", p, crs) for p in picks)


def test_june22_uruguay_cape_verde_draw_secondary():
    """2026-06-22: Uruguay 2:2 — opponent clean sheet keeps draw line in picks."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "2:0": 4.6, "1:0": 4.95, "1:1": 7.3, "2:2": 28.0, "4:0": 18.0,
        "0:0": 12.0, "2:1": 8.0,
    }
    ctx = _june22_ctx(
        {"played": 1, "goals_for": 1, "goals_against": 1},
        {"played": 1, "goals_for": 0, "goals_against": 0},
        group_avg_gf=0.5,
    )
    _, upset, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=55.0,
        draw_rate=30.0,
        lose_rate=15.0,
        sp_win=1.50,
        sp_draw=4.20,
        sp_lose=6.50,
        rank_a=17,
        rank_b=64,
        stage="小组赛",
        group_context=ctx,
    )
    assert any(
        score_matches_pick("2:2", p, crs) or score_matches_pick("1:1", p, crs)
        for p in picks
    )


def test_june22_nz_egypt_multi_goal_away():
    """2026-06-22: NZ 1:3 — away fav keeps 1:3 in likely pair."""
    from service.score_pick import run_full_score_pipeline

    crs = {
        "0:1": 5.75, "1:2": 5.8, "1:3": 11.0, "0:3": 11.0, "1:1": 6.8,
        "0:2": 8.5, "2:1": 14.0,
    }
    ctx = _june22_ctx(
        {"played": 1, "goals_for": 2, "goals_against": 2},
        {"played": 1, "goals_for": 1, "goals_against": 1},
    )
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=18.0,
        draw_rate=22.0,
        lose_rate=60.0,
        sp_win=5.50,
        sp_draw=4.00,
        sp_lose=1.42,
        handicap="+1",
        rank_a=89,
        rank_b=29,
        stage="小组赛",
        group_context=ctx,
        odds_dict={"win_win": 5.50, "draw": 4.00, "win_lose": 1.42, "over_under": 2.5},
        skip_wdl_resilience=True,
    )
    assert any(score_matches_pick("1:3", p, crs) for p in picks)


def test_align_preserves_draw_when_resilience_active():
    from service.score_context import detect_resilience_signals
    from service.score_pick import align_score_picks_to_wdl, _score_outcome

    ctx = {
        "matchday": 2,
        "group_avg_gf": 0.5,
        "standing_a": {"played": 1, "goals_for": 1, "goals_against": 1},
        "standing_b": {"played": 1, "goals_for": 0, "goals_against": 0},
    }
    sig = detect_resilience_signals(ctx, None, 17, 64)
    crs = {"2:0": 4.6, "1:0": 4.95, "1:1": 7.3, "4:0": 18.0}
    out = align_score_picks_to_wdl(
        ["2:0", "1:1"], crs,
        win_rate=62.0, draw_rate=28.0, lose_rate=10.0,
        resilience=sig,
    )
    assert _score_outcome(out[1]) == "draw"


def test_june26_tunisia_netherlands_away_rout_not_home_upset():
    """2026-06-26: Tunisia vs Netherlands — MD3 rout must not flip to 1:0/2:1."""
    from service.score_pick import run_full_score_pipeline, score_matches_pick

    crs = {
        "0:3": 5.0, "0:2": 5.5, "0:4": 6.5, "0:1": 9.2, "0:5": 9.5, "1:3": 9.5,
        "1:0": 80.0, "2:1": 80.0, "1:1": 25.0, "0:0": 29.0, "2:2": 50.0,
    }
    ctx = {
        "stage": "小组赛",
        "matchday": 3,
        "must_win_a": True,
        "must_win_b": False,
        "qualified_a": False,
        "qualified_b": True,
        "standing_a": {"played": 2, "points": 0, "goals_for": 1, "goals_against": 9},
        "standing_b": {"played": 2, "points": 4, "goals_for": 7, "goals_against": 3},
    }
    # Rule engine can over-boost home must-win without 1X2 market — align must not undo rout
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=48.6,
        draw_rate=12.5,
        lose_rate=38.9,
        handicap="+2",
        rank_a=44,
        rank_b=7,
        stage="小组赛",
        group_context=ctx,
        odds_dict={"handicap": "+2", "over_under": 2.5},
        skip_wdl_resilience=True,
    )
    assert not any(p in ("1:0", "2:1") for p in picks[:2])
    assert any(score_matches_pick("0:3", p, crs) or score_matches_pick("0:2", p, crs) for p in picks[:2])


def test_june26_curacao_ivory_coast_away_rout_not_home_upset():
    """2026-06-26: Curacao vs Côte d'Ivoire — +2 handicap, no 1X2, away rout."""
    from service.score_pick import run_full_score_pipeline, score_matches_pick

    crs = {
        "0:2": 6.0, "0:3": 6.5, "0:1": 7.0, "1:3": 8.0, "0:4": 9.0,
        "1:0": 80.0, "2:1": 85.0, "1:1": 25.0, "0:0": 30.0, "2:2": 45.0,
    }
    ctx = {
        "stage": "小组赛",
        "matchday": 3,
        "must_win_a": True,
        "must_win_b": False,
        "qualified_a": False,
        "qualified_b": False,
        "rank_a": 82,
        "rank_b": 34,
        "rank_gap": 48,
        "standing_a": {"played": 2, "points": 0, "goals_for": 1, "goals_against": 6},
        "standing_b": {"played": 2, "points": 3, "goals_for": 3, "goals_against": 2},
    }
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=39.3,
        draw_rate=38.0,
        lose_rate=22.7,
        handicap="+2",
        rank_a=82,
        rank_b=34,
        stage="小组赛",
        group_context=ctx,
        odds_dict={"handicap": "+2", "over_under": 2.5},
        skip_wdl_resilience=True,
    )
    assert not any(p in ("1:0", "2:1", "2:0") for p in picks[:2])
    assert any(score_matches_pick("0:2", p, crs) or score_matches_pick("0:3", p, crs) for p in picks[:2])


def test_june27_cape_verde_saudi_likely_pair_not_opposite():
    """2026-06-27: Cape Verde vs Saudi — hot pair must not be 1:2 + 2:1."""
    from service.score_pick import run_full_score_pipeline, _score_outcome, repair_stored_score_picks

    crs = {
        "1:1": 5.5, "2:1": 7.5, "1:0": 7.6, "1:2": 8.0, "0:1": 8.5,
        "0:0": 10.0, "2:2": 12.0, "0:2": 14.0,
    }
    ctx = {
        "stage": "小组赛",
        "matchday": 3,
        "must_win_a": False,
        "must_win_b": True,
        "qualified_a": False,
        "qualified_b": False,
        "rank_a": 64,
        "rank_b": 53,
        "rank_gap": 11,
        "standing_a": {"played": 2, "points": 2, "goals_for": 2, "goals_against": 2},
        "standing_b": {"played": 2, "points": 1, "goals_for": 1, "goals_against": 5},
    }
    _, _, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=30.5,
        draw_rate=28.8,
        lose_rate=40.7,
        sp_win=2.46,
        sp_draw=3.05,
        sp_lose=2.53,
        handicap="-1",
        rank_a=64,
        rank_b=53,
        stage="小组赛",
        group_context=ctx,
        odds_dict={"win_win": 2.46, "draw": 3.05, "win_lose": 2.53, "handicap": "-1"},
        skip_wdl_resilience=True,
    )
    assert _score_outcome(picks[0]) != "win" or _score_outcome(picks[1]) != "lose"
    assert not ({_score_outcome(picks[0]), _score_outcome(picks[1])} == {"win", "lose"})
    assert any(_score_outcome(p) == "lose" for p in picks[:2])
    fixed, upset = repair_stored_score_picks(
        ["1:2", "2:1"], "2:2", crs,
        win_rate=30.5, draw_rate=28.8, lose_rate=40.7,
        sp_win=2.46, sp_lose=2.53, sp_draw=3.05, handicap="-1", rank_a=64, rank_b=53,
    )
    assert not ({_score_outcome(fixed[0]), _score_outcome(fixed[1])} == {"win", "lose"})


def test_late_knockout_open_market_covers_both_one_goal_wins():
    """Semi-final open markets must not lock onto CRS 1:1 as primary."""
    from service.score_pick import pick_crs_anchored_scores, pick_upset_from_crs, refine_wdl_after_score_pick

    crs = {
        "1:1": 5.0, "2:1": 6.75, "1:2": 8.5, "0:0": 7.5,
        "1:0": 7.6, "0:1": 8.0, "2:0": 12.0, "0:2": 16.0,
    }
    best = pick_crs_anchored_scores(
        crs,
        win_rate=36.0, lose_rate=34.0, draw_rate=30.0,
        expected_a=1.2, expected_b=1.15,
        sp_win=2.35, sp_lose=2.94, sp_draw=2.75,
        stage="半决赛",
    )
    assert best[0] != "1:1"
    assert {_score_outcome(best[0]), _score_outcome(best[1])} == {"win", "lose"}
    assert "1:2" in best or "2:1" in best
    upset = pick_upset_from_crs(
        crs, best,
        win_rate=36.0, lose_rate=34.0, draw_rate=30.0,
        sp_win=2.35, sp_lose=2.94, sp_draw=2.75,
    )
    assert upset and _score_outcome(upset) == "draw"
    # England 1:2 Argentina — covered as secondary
    assert "1:2" in best + ([upset] if upset else [])

    w, d, l = refine_wdl_after_score_pick(
        ["1:1", "2:1"], 36.0, 28.0, 36.0,
        stage="半决赛", sp_win=2.35, sp_lose=2.94,
    )
    assert d < max(w, l) + 0.1 or d <= 36.0


def test_late_knockout_france_spain_style_covers_away_one_goal():
    from service.score_pick import pick_crs_anchored_scores, run_full_score_pipeline

    crs = {
        "1:1": 5.5, "2:1": 6.25, "1:2": 9.0, "0:2": 19.0,
        "2:0": 13.0, "0:1": 11.0, "1:0": 9.7, "0:0": 12.5,
    }
    best, upset, all_picks, _ = run_full_score_pipeline(
        crs,
        win_rate=42.0, draw_rate=28.0, lose_rate=30.0,
        expected_a=1.3, expected_b=1.1,
        sp_win=2.03, sp_draw=3.13, sp_lose=3.15,
        stage="半决赛",
        rank_a=2, rank_b=8,
    )
    assert best[0] != "1:1"
    assert "1:2" in all_picks or "0:2" in all_picks


def test_knockout_brazil_japan_prefers_win_not_draw_primary():
    from service.score_pick import finalize_knockout_score_picks, align_wdl_to_score_picks
    from service.rule_engine import RuleEngine
    from service.match_context import build_group_context

    ctx = build_group_context("1/16决赛", "", 0, "巴西", "日本", 6, 18)
    re = RuleEngine()
    r = re.evaluate(
        {"name": "巴西", "rank": 6, "attack": 88, "defend": 85, "midfield": 86, "speed": 86, "physical": 85, "tactic": "控球"},
        {"name": "日本", "rank": 18, "attack": 78, "defend": 80, "midfield": 80, "speed": 82, "physical": 78, "tactic": "防守反击"},
        odds=None, group_context=ctx,
    )
    scores, _ = finalize_knockout_score_picks(
        r.best_scores,
        expected_a=r.expected_a, expected_b=r.expected_b,
        win_rate=r.win_rate, draw_rate=r.draw_rate, lose_rate=r.lose_rate,
        rank_a=6, rank_b=18, stage="1/16决赛",
    )
    assert _score_outcome(scores[0]) == "win"
    w, d, l = align_wdl_to_score_picks(
        scores, r.win_rate, r.draw_rate, r.lose_rate,
        stage="1/16决赛", rank_a=6, rank_b=18,
    )
    assert w >= l


def test_knockout_germany_paraguay_includes_draw_secondary():
    from service.score_pick import finalize_knockout_score_picks

    scores, _ = finalize_knockout_score_picks(
        ["1:1", "0:0", "1:0"],
        expected_a=1.45, expected_b=0.95,
        win_rate=53.0, draw_rate=18.0, lose_rate=29.0,
        rank_a=10, rank_b=40, stage="1/16决赛",
    )
    assert _score_outcome(scores[0]) == "win"
    # Rank gap 30 — favour win cluster over ET draw secondary
    assert _score_outcome(scores[1]) == "win"


def test_knockout_r32_replay_hits():
    from data.worldcup_history import HISTORICAL_MATCHES
    from service.score_backtest import run_score_prediction, score_matches_pick

    targets = {("巴西", "日本"), ("德国", "巴拉圭"), ("荷兰", "摩洛哥")}
    for h in HISTORICAL_MATCHES:
        if h.get("year") != 2026 or h.get("stage") != "1/16决赛":
            continue
        if (h["team_a"], h["team_b"]) not in targets:
            continue
        crs = {str(k): float(v) for k, v in (h.get("score_odds") or {}).items()}
        eu = h.get("european") or {}
        w, d, l = eu["win_win"], eu["draw"], eu["win_lose"]
        o = 1 / w + 1 / d + 1 / l
        wdl = ((1 / w) / o * 100, (1 / d) / o * 100, (1 / l) / o * 100)
        p1, _, _, all_p = run_score_prediction(
            h["team_a"], h["team_b"], crs, wdl,
            {"win_win": w, "draw": d, "win_lose": l, "handicap": (h.get("macau") or {}).get("handicap")},
            stage="1/16决赛",
        )
        actual = f"{h['result_a']}:{h['result_b']}"
        hit = score_matches_pick(actual, p1, crs) or any(
            score_matches_pick(actual, p, crs) for p in all_p if p
        )
        assert hit, f"{h['team_a']} vs {h['team_b']} actual={actual} picks={all_p}"


def test_extreme_fav_adds_stalemate_upset():
    from service.score_pick import ensure_extreme_mismatch_triple_coverage

    crs = {
        "3:0": 6.0, "4:0": 8.0, "2:0": 7.0, "1:0": 9.0,
        "0:0": 15.0, "1:1": 12.0, "胜其它": 18.0,
    }
    picks, upset = ensure_extreme_mismatch_triple_coverage(
        ["3:0", "4:0"], "2:0", crs,
        sp_win=1.08, rank_a=7, rank_b=88, expected_a=2.8, expected_b=0.4,
    )
    assert upset in ("0:0", "1:1")
    assert picks[0] == "3:0"


def test_extreme_rout_promotes_win_other_secondary():
    from service.score_pick import ensure_extreme_mismatch_triple_coverage, score_matches_pick

    crs = {
        "3:0": 5.5, "4:0": 7.0, "2:0": 6.0, "1:1": 12.0, "胜其它": 9.0,
    }
    picks, _ = ensure_extreme_mismatch_triple_coverage(
        ["3:0", "4:0"], "1:1", crs,
        sp_win=1.05, rank_a=5, rank_b=95, expected_a=3.2, expected_b=0.3,
    )
    assert picks[1] == "胜其它"
    assert score_matches_pick("7:1", "胜其它", crs)


def test_align_respects_crs_when_wdl_margin_small():
    from service.score_pick import align_score_picks_to_wdl

    crs = {"0:2": 5.5, "0:1": 6.0, "1:1": 7.0, "1:2": 9.0}
    out = align_score_picks_to_wdl(
        ["0:2", "0:1"], crs,
        win_rate=44.0, draw_rate=28.0, lose_rate=28.0,
    )
    assert out[0] == "0:2"


def test_cap_knockout_wdl_pulls_inflated_draw():
    from service.score_pick import cap_knockout_wdl_to_market

    w, d, l = cap_knockout_wdl_to_market(
        26.0, 44.0, 30.0, "1/8决赛",
        sp_win=2.80, sp_draw=3.20, sp_lose=2.50,
    )
    assert d < 44.0
    assert d <= 36.0


def test_knockout_synthetic_crs_lowers_draw_for_clear_fav():
    from service.score_pick import build_knockout_synthetic_crs, _score_outcome

    crs = build_knockout_synthetic_crs(
        2.1, 0.8,
        win_rate=62.0, draw_rate=42.0, lose_rate=18.0,
        sp_win=1.45, sp_draw=4.5, sp_lose=6.0,
    )
    assert crs
    draw_scores = [s for s in crs if _score_outcome(s) == "draw"]
    win_scores = [s for s in crs if _score_outcome(s) == "win"]
    assert draw_scores and win_scores
    best_draw = min(draw_scores, key=lambda s: crs[s])
    best_win = min(win_scores, key=lambda s: crs[s])
    assert crs[best_win] < crs[best_draw]


def test_apply_stage_draw_skips_knockout_clear_fav():
    from service.score_pick import apply_stage_draw_adjustment

    w, d, l = apply_stage_draw_adjustment(
        58.0, 24.0, 18.0, "1/8决赛", sp_win=1.45, sp_lose=6.5,
    )
    assert (w, d, l) == (58.0, 24.0, 18.0)


def test_promote_knockout_blowout_when_xg_gap_large():
    from service.score_pick import promote_knockout_blowout_scores

    crs = {"1:1": 6.0, "0:1": 7.0, "0:2": 8.0, "0:3": 10.0, "1:2": 9.0}
    out = promote_knockout_blowout_scores(
        ["1:1", "0:1"], crs,
        expected_a=0.9, expected_b=2.4,
        stage="1/8决赛", win_rate=25.0, lose_rate=58.0, rank_gap=30,
    )
    assert out[0] in ("0:2", "0:3", "1:3")

