"""Conservative league score mode: early-season / no-book safeguards."""
from service.match_context import build_group_context
from service.rule_engine import RuleEngine
from service.score_pick import run_full_score_pipeline
from service.score_pipeline.upset_picker import UpsetPicker
from service.score_pipeline.base import AggregatedScore, ScorerInput


def _club(name: str, rank: int, tactic: str = "传控") -> dict:
    pct = max(0.0, 1.0 - (rank - 1) / 19.0)
    base = 62 + pct * 28
    return {
        "name": name,
        "rank": rank,
        "attack": round(base + pct * 6),
        "defend": round(base - (1 - pct) * 4),
        "midfield": round(base),
        "speed": round(base - 2),
        "physical": round(base - 1),
        "tactic": tactic,
    }


def test_early_season_flag_on_matchday_one():
    ctx = build_group_context(
        "第1轮", "", 1, "马竞", "马拉加", 3, 20, home_side_override="a",
    )
    assert ctx["is_league"] is True
    assert ctx["early_season"] is True
    ctx_late = build_group_context(
        "第12轮", "", 12, "马竞", "马拉加", 3, 20, home_side_override="a",
    )
    assert ctx_late["early_season"] is False


def test_no_book_early_season_avoids_extreme_away_xg():
    engine = RuleEngine()
    home = _club("马竞", 3)
    away = _club("马拉加", 20, "防守反击")
    ctx = build_group_context(
        "第1轮", "", 1, "马竞", "马拉加", 3, 20, home_side_override="a",
    )
    ctx["has_book_odds"] = False
    result = engine.evaluate(home, away, group_context=ctx)
    assert result.expected_b >= 0.65
    assert result.expected_a - result.expected_b < 2.2
    assert result.draw_rate >= 24.0


def test_synthetic_crs_pipeline_prefers_narrow_wins_over_4_0():
    home = _club("塞维利亚", 8)
    away = _club("巴列卡诺", 12)
    ctx = build_group_context(
        "第1轮", "", 1, home["name"], away["name"], 8, 12, home_side_override="a",
    )
    ctx["has_book_odds"] = False
    engine = RuleEngine()
    rule = engine.evaluate(home, away, group_context=ctx)
    best, upset, all_picks, _ = run_full_score_pipeline(
        {},
        win_rate=rule.win_rate,
        draw_rate=rule.draw_rate,
        lose_rate=rule.lose_rate,
        expected_a=rule.expected_a,
        expected_b=rule.expected_b,
        stage="第1轮",
        rank_a=8,
        rank_b=12,
        group_context=ctx,
        odds_dict={"has_real_market": False},
        team_a=home,
        team_b=away,
    )
    assert best
    assert "4:0" not in best
    assert upset not in set(best)


def test_upset_picker_never_duplicates_likely_pair():
    picker = UpsetPicker()
    aggregated = [
        AggregatedScore("3:0", 1.0, {"poisson": 1.0}),
        AggregatedScore("3:1", 0.8, {"poisson": 0.8}),
        AggregatedScore("1:1", 0.5, {"poisson": 0.5}),
        AggregatedScore("2:1", 0.4, {"poisson": 0.4}),
    ]
    crs = {"3:0": 5.0, "3:1": 6.0, "1:1": 8.0, "2:1": 7.0}
    inp = ScorerInput(
        score_odds=crs,
        win_rate=60.0,
        draw_rate=20.0,
        lose_rate=20.0,
        expected_a=2.0,
        expected_b=0.9,
    )
    upset = picker.pick(aggregated, ["3:0", "3:1"], crs, inp)
    assert upset not in {"3:0", "3:1"}


def test_best_draw_prefers_low_scoring_draws():
    from service.score_pick import _best_draw, _rank_crs

    crs = {"2:2": 7.0, "1:1": 8.5, "0:0": 9.0, "2:1": 6.0}
    ranked = _rank_crs(crs, set())
    assert _best_draw(ranked, set()) == "0:0"
    assert _best_draw(ranked, {"0:0"}) == "1:1"


def test_away_favourite_trio_includes_away_score():
    from service.score_pick import ensure_market_direction_in_trio

    crs = {
        "2:1": 8.0, "1:0": 9.0, "2:0": 10.0,
        "0:1": 5.5, "0:2": 7.0, "1:2": 6.5,
        "1:1": 7.5, "0:0": 11.0, "2:2": 14.0,
    }
    best, upset = ensure_market_direction_in_trio(
        ["2:1", "1:0"], "2:2", crs,
        win_rate=22.0, draw_rate=24.0, lose_rate=54.0,
        sp_win=4.05, sp_draw=3.75, sp_lose=1.63,
    )
    trio = set(best) | ({upset} if upset else set())
    assert any(
        ":" in s and int(s.split(":")[1]) > int(s.split(":")[0])
        for s in trio
    ), trio
    if upset and ":" in upset and upset.split(":")[0] == upset.split(":")[1]:
        assert upset in ("0:0", "1:1"), upset


def test_strong_home_fav_upset_prefers_low_draw():
    from service.score_pick import ensure_market_direction_in_trio

    crs = {
        "2:1": 5.0, "2:0": 6.0, "1:0": 7.0,
        "1:1": 8.0, "0:0": 9.5, "2:2": 12.0,
    }
    best, upset = ensure_market_direction_in_trio(
        ["2:1", "2:0"], "2:2", crs,
        win_rate=58.0, draw_rate=24.0, lose_rate=18.0,
        sp_win=1.62, sp_draw=3.36, sp_lose=4.66,
    )
    assert best[1] == "1:0"
    assert upset in ("0:0", "1:1")


def test_run_score_prediction_uses_european_wdl_when_missing():
    from service.score_backtest import run_score_prediction

    crs = {
        "2:1": 9.0, "1:0": 10.0, "2:0": 11.0,
        "0:1": 5.0, "1:2": 6.0, "0:2": 7.5,
        "1:1": 8.0, "0:0": 12.0, "2:2": 15.0,
    }
    p1, p2, upset, all_picks = run_score_prediction(
        "富勒姆", "切尔西", crs, None,
        {"win_win": 4.05, "draw": 3.75, "win_lose": 1.63},
        stage="第1轮",
        competition_slug="premier-league",
        matchday=1,
    )
    trio = [p for p in [p1, p2, upset] if p and p != "-"]
    assert any(
        ":" in s and int(s.split(":")[1]) > int(s.split(":")[0])
        for s in trio
    ), (p1, p2, upset, all_picks)


def test_osasuna_style_keeps_crs_draw_in_trio():
    from service.score_pick import run_full_score_pipeline, _score_outcome

    crs = {
        "1:1": 6.4, "1:0": 6.5, "2:1": 7.0, "2:0": 7.75,
        "0:0": 10.5, "0:1": 12.5, "1:2": 13.0, "3:0": 13.0,
    }
    home = _club("奥萨苏纳", 11)
    away = _club("莱万特", 17)
    ctx = build_group_context(
        "第2轮", "", 2, "奥萨苏纳", "莱万特", 11, 17, home_side_override="a",
    )
    ctx["has_book_odds"] = True
    best, upset, all_picks, _ = run_full_score_pipeline(
        crs,
        win_rate=54.7, draw_rate=26.3, lose_rate=19.0,
        expected_a=1.6, expected_b=1.0,
        stage="第2轮",
        sp_win=1.62, sp_draw=3.36, sp_lose=4.66,
        handicap="-1",
        rank_a=11, rank_b=17,
        group_context=ctx,
        odds_dict={"win_win": 1.62, "draw": 3.36, "win_lose": 4.66, "has_real_market": True},
        team_a=home, team_b=away,
    )
    trio = [s for s in (best + [upset]) if s]
    assert any(_score_outcome(s) == "draw" for s in trio[:2]), (best, upset)
    assert any(_score_outcome(s) == "draw" for s in trio), (best, upset)


def test_roma_style_does_not_lead_with_three_nil():
    from service.score_pick import run_full_score_pipeline, _score_outcome

    crs = {
        "1:0": 6.7, "1:1": 7.0, "2:1": 7.0, "2:0": 7.5,
        "3:0": 11.0, "0:0": 12.0, "3:1": 12.0, "0:1": 14.0,
    }
    home = _club("罗马", 6)
    away = _club("佛罗伦萨", 8)
    ctx = build_group_context(
        "第1轮", "", 1, "罗马", "佛罗伦萨", 6, 8, home_side_override="a",
    )
    ctx["has_book_odds"] = True
    best, upset, _, _ = run_full_score_pipeline(
        crs,
        win_rate=57.5, draw_rate=24.9, lose_rate=17.5,
        expected_a=1.71, expected_b=1.2,
        stage="第1轮",
        sp_win=1.54, sp_draw=3.55, sp_lose=5.05,
        handicap="-1",
        rank_a=6, rank_b=8,
        group_context=ctx,
        odds_dict={"win_win": 1.54, "draw": 3.55, "win_lose": 5.05, "has_real_market": True},
        team_a=home, team_b=away,
    )
    assert best
    assert best[0] != "3:0"
    assert _score_outcome(best[0]) == "win"
    trio = [s for s in best + [upset] if s]
    home_wins = [s for s in trio if _score_outcome(s) == "win"]
    totals = set()
    for s in home_wins:
        a, b = map(int, s.split(":"))
        totals.add(a + b)
    assert len(totals) >= 1


def test_chelsea_away_fav_spreads_or_covers_three_directions():
    from service.score_pick import run_full_score_pipeline, _score_outcome

    crs = {
        "1:2": 6.75, "1:1": 7.5, "0:1": 8.5, "0:2": 9.0,
        "1:3": 12.0, "2:2": 12.5, "2:1": 13.0, "0:0": 14.0, "2:3": 16.0,
    }
    home = _club("富勒姆", 11)
    away = _club("切尔西", 4)
    ctx = build_group_context(
        "第1轮", "", 1, "富勒姆", "切尔西", 11, 4, home_side_override="a",
    )
    ctx["has_book_odds"] = True
    best, upset, _, _ = run_full_score_pipeline(
        crs,
        win_rate=21.9, draw_rate=23.7, lose_rate=54.4,
        expected_a=1.36, expected_b=1.58,
        stage="第1轮",
        sp_win=4.05, sp_draw=3.75, sp_lose=1.63,
        handicap="+1",
        rank_a=11, rank_b=4,
        group_context=ctx,
        odds_dict={"win_win": 4.05, "draw": 3.75, "win_lose": 1.63, "has_real_market": True},
        team_a=home, team_b=away,
    )
    trio = [s for s in (best + [upset]) if s]
    outs = {_score_outcome(s) for s in trio}
    away_scores = [s for s in trio if _score_outcome(s) == "lose"]
    stacked_low = set(trio) <= {"1:2", "0:2", "1:1", "0:1"}
    assert "lose" in outs, (best, upset)
    assert len(outs) >= 2, (best, upset)
    assert (not stacked_low) or len(outs) >= 3 or any(s in {"1:3", "2:3", "2:1"} for s in trio), (
        best, upset, away_scores,
    )


def test_even_league_game_covers_narrow_away():
    from service.score_pick import run_full_score_pipeline, poisson_to_synthetic_crs, _score_outcome

    home = _club("瓦伦西亚", 9)
    away = _club("贝蒂斯", 6)
    ctx = build_group_context(
        "第1轮", "", 1, "瓦伦西亚", "贝蒂斯", 9, 6, home_side_override="a",
    )
    ctx["has_book_odds"] = False
    engine = RuleEngine()
    rule = engine.evaluate(home, away, group_context=ctx)
    assert rule.draw_rate >= 24.0
    crs = poisson_to_synthetic_crs(rule.expected_a, rule.expected_b, rule.draw_rate)
    best, upset, _, _ = run_full_score_pipeline(
        crs,
        win_rate=rule.win_rate, draw_rate=rule.draw_rate, lose_rate=rule.lose_rate,
        expected_a=rule.expected_a, expected_b=rule.expected_b,
        stage="第1轮",
        rank_a=9, rank_b=6,
        group_context=ctx,
        odds_dict={"has_real_market": False},
        team_a=home, team_b=away, rule_result=rule,
    )
    trio = [s for s in (best + [upset]) if s]
    assert "0:1" in trio or any(_score_outcome(s) == "lose" for s in trio), (best, upset, rule.draw_rate)


def test_no_book_close_match_does_not_make_draw_favourite():
    """Blind league close games must not mass-promote 1:1 as WDL favourite."""
    engine = RuleEngine()
    home = _club("纽卡斯尔", 8)
    away = _club("水晶宫", 11)
    ctx = build_group_context(
        "第5轮", "", 5, home["name"], away["name"], 8, 11, home_side_override="a",
    )
    ctx["has_book_odds"] = False
    rule = engine.evaluate(home, away, group_context=ctx)
    assert rule.draw_rate >= 24.0
    assert rule.draw_rate <= 34.0
    assert rule.draw_rate < max(rule.win_rate, rule.lose_rate)


def test_no_book_home_edge_spreads_beyond_2_1_2_0_template():
    from service.score_pick import run_full_score_pipeline, poisson_to_synthetic_crs, _score_outcome

    home = _club("马竞", 3)
    away = _club("赫塔费", 14)
    ctx = build_group_context(
        "第5轮", "", 5, home["name"], away["name"], 3, 14, home_side_override="a",
    )
    ctx["has_book_odds"] = False
    engine = RuleEngine()
    rule = engine.evaluate(home, away, group_context=ctx)
    assert rule.win_rate > rule.draw_rate
    assert rule.win_rate > rule.lose_rate
    crs = poisson_to_synthetic_crs(rule.expected_a, rule.expected_b, rule.draw_rate)
    best, upset, _, _ = run_full_score_pipeline(
        crs,
        win_rate=rule.win_rate, draw_rate=rule.draw_rate, lose_rate=rule.lose_rate,
        expected_a=rule.expected_a, expected_b=rule.expected_b,
        stage="第5轮",
        rank_a=3, rank_b=14,
        group_context=ctx,
        odds_dict={"has_real_market": False},
        team_a=home, team_b=away, rule_result=rule,
    )
    assert best and _score_outcome(best[0]) == "win"
    assert best[0] != "1:1"
    # Must not collapse into the old rigid 2:1|2:0|1:1 only ladder.
    assert not (set(best) == {"2:1", "2:0"} and upset == "1:1"), (best, upset)
    assert "1:0" in (best + [upset]) or best[0] in {"1:0", "2:0", "2:1"}, (best, upset)


def test_derive_crs_when_euro_only():
    from crawler.odds_scraper import derive_score_odds
    from crawler.odds_crawler import _has_crs_data

    crs = derive_score_odds(1.85, 3.60, 4.20)
    assert _has_crs_data(crs)
    assert "1:0" in crs and "1:1" in crs and "0:1" in crs
