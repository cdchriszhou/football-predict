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
    assert result.draw_rate >= 18.0


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
