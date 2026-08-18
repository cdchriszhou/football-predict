"""Unit tests for CRS-anchored score selection fixes."""
from service.score_pick import (
    pick_crs_anchored_scores,
    reconcile_likely_upset_cluster,
    repair_stored_score_picks,
    score_matches_pick,
    _score_outcome,
)

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

def _june22_ctx(standing_a, standing_b, group_avg_gf=1.5):
    return {
        "stage": "小组赛",
        "matchday": 2,
        "group_avg_gf": group_avg_gf,
        "standing_a": standing_a,
        "standing_b": standing_b,
    }

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

