"""Tests for score backtest service."""
import pytest

from service.score_backtest import (
    run_score_prediction,
    _evaluate_match,
    build_daily_report,
    _backtest_group_key_label,
    _resolve_kickoff,
    _odds_meta_from_history,
)
from data.worldcup_schedule_lookup import canonical_kickoff_beijing
from service.score_pick import score_matches_pick


def _sample_row(date: str, primary_hit: bool, triple_hit: bool, matchday: int = 1) -> dict:
    return {
        "match_time": f"{date}T20:00:00",
        "matchday": matchday,
        "primary_hit": primary_hit,
        "triple_hit": triple_hit,
        "team_a": "A",
        "team_b": "B",
        "actual_score": "1:0",
        "primary_pick": "1:0",
        "secondary_pick": "2:0",
        "upset_pick": "0:1",
    }


def test_build_daily_report_groups_by_date():
    rows = [
        _sample_row("2026-06-17", True, True),
        _sample_row("2026-06-17", False, True),
        _sample_row("2026-06-18", False, False),
    ]
    report = build_daily_report(rows, days=14)
    assert len(report["days"]) == 2
    june17 = next(d for d in report["days"] if d["date"] == "2026-06-17")
    assert june17["evaluated"] == 2
    assert june17["primary_hits"] == 1
    assert june17["triple_hits"] == 2
    assert june17["primary_hit_rate"] == 50.0
    assert june17["triple_hit_rate"] == 100.0
    assert report["summary"]["total_evaluated"] == 3


def test_build_daily_report_respects_days_limit():
    rows = [
        _sample_row("2026-06-15", True, True),
        _sample_row("2026-06-16", True, True),
        _sample_row("2026-06-17", True, True),
    ]
    report = build_daily_report(rows, days=2)
    assert len(report["days"]) == 2
    assert report["days"][-1]["date"] == "2026-06-17"


def test_backtest_prefers_date_for_worldcup_rows():
    row = _sample_row("2026-06-17", True, True, matchday=1)
    key, label = _backtest_group_key_label(row, prefer_date=True)
    assert key == "d2026-06-17"
    assert label == "2026-06-17"


def test_canada_draw_primary():
    crs = {
        "1:1": 4.75, "1:0": 5.10, "2:1": 5.30, "2:0": 6.60,
        "0:0": 9.50, "0:1": 11.00,
    }
    odds = {"win_win": 1.62, "draw": 3.32, "win_lose": 4.75, "handicap": "-1"}
    wdl = (41.0, 41.5, 17.5)
    p1, p2, _, _ = run_score_prediction("加拿大", "波黑", crs, wdl, odds)
    assert p1 == "1:1"
    assert score_matches_pick("1:1", p1, crs)


def test_uzbekistan_colombia_cluster_prefers_concession():
    from data.worldcup_history import HISTORICAL_MATCHES
    from service.score_pick import refine_favorite_score_cluster

    hist = next(
        m for m in HISTORICAL_MATCHES
        if m.get("year") == 2026 and m["team_a"] == "乌兹别克斯坦" and m["team_b"] == "哥伦比亚"
    )
    crs = {str(k): float(v) for k, v in hist["score_odds"].items()}
    base = ["0:2", "1:1"]
    refined = refine_favorite_score_cluster(
        base, crs, win_rate=12.0, lose_rate=66.9, sp_win=7.5, sp_lose=1.35,
    )
    assert refined == ["0:2", "1:3"]
    moderate = refine_favorite_score_cluster(
        base, crs, win_rate=33.0, lose_rate=56.0, sp_win=7.5, sp_lose=1.35,
    )
    assert moderate == ["0:2", "1:2"]


def test_evaluate_match_uses_published_picks():
    crs = {"0:2": 5.7, "1:3": 8.5, "1:1": 10.5}
    row = _evaluate_match(
        team_a="乌兹别克斯坦",
        team_b="哥伦比亚",
        actual="1:3",
        crs=crs,
        wdl=None,
        odds_meta=None,
        published_picks=("0:2", "1:3", None, ["0:2", "1:3"]),
    )
    assert row["pick_source"] == "published"
    assert row["secondary_pick"] == "1:3"
    assert row["triple_hit"] is True

    assert _evaluate_match(
        team_a="A", team_b="B", actual="1:0", crs={}, wdl=None, odds_meta=None,
    ) is None


def test_ghana_panama_kickoff_is_june18_beijing():
    kickoff = canonical_kickoff_beijing("加纳", "巴拿马")
    assert kickoff is not None
    assert kickoff.strftime("%Y-%m-%d") == "2026-06-18"
    assert kickoff.hour == 7


def test_june18_daily_report_has_four_matches():
    """Official schedule has 4 group-stage fixtures on 2026-06-18 (Beijing)."""
    from data.worldcup_history import HISTORICAL_MATCHES
    from service.score_backtest import _evaluate_match, _resolve_kickoff, build_daily_report

    rows = []
    j18_pairs = {
        ("葡萄牙", "刚果(金)"),
        ("乌兹别克斯坦", "哥伦比亚"),
        ("英格兰", "克罗地亚"),
        ("加纳", "巴拿马"),
    }
    for hist in HISTORICAL_MATCHES:
        if hist.get("year") != 2026:
            continue
        if (hist["team_a"], hist["team_b"]) not in j18_pairs:
            continue
        crs = {str(k): float(v) for k, v in hist["score_odds"].items()}
        kickoff = _resolve_kickoff(hist["team_a"], hist["team_b"], None, hist)
        row = _evaluate_match(
            team_a=hist["team_a"],
            team_b=hist["team_b"],
            actual=f"{hist['result_a']}:{hist['result_b']}",
            crs=crs,
            wdl=(50.0, 25.0, 25.0),
            odds_meta=_odds_meta_from_history(hist),
            match_time=kickoff,
            stage=hist.get("stage") or "",
            group_name=hist.get("group_name"),
            matchday=hist.get("matchday"),
        )
        assert row is not None
        rows.append(row)

    report = build_daily_report(rows, days=14)
    june18 = next(d for d in report["days"] if d["date"] == "2026-06-18")
    assert june18["evaluated"] == 4
    teams = {(m["team_a"], m["team_b"]) for m in june18["matches"]}
    assert teams == j18_pairs

