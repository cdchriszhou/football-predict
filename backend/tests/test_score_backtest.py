"""Tests for score backtest service."""
import asyncio
from datetime import datetime

from service.score_backtest import (
    run_score_prediction,
    _evaluate_match,
    build_daily_report,
    _backtest_group_key_label,
    _collect_evaluated_rows,
    _is_worldcup_competition,
    _notes_for,
    LEAGUE_NOTES,
)
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
        _sample_row("2026-08-16", True, True),
        _sample_row("2026-08-16", False, True),
        _sample_row("2026-08-17", False, False),
    ]
    report = build_daily_report(rows, days=14)
    assert len(report["days"]) == 2
    day16 = next(d for d in report["days"] if d["date"] == "2026-08-16")
    assert day16["evaluated"] == 2
    assert day16["primary_hits"] == 1
    assert day16["triple_hits"] == 2
    assert day16["primary_hit_rate"] == 50.0
    assert day16["triple_hit_rate"] == 100.0
    assert report["summary"]["total_evaluated"] == 3


def test_build_daily_report_respects_days_limit():
    rows = [
        _sample_row("2026-08-15", True, True),
        _sample_row("2026-08-16", True, True),
        _sample_row("2026-08-17", True, True),
    ]
    report = build_daily_report(rows, days=2)
    assert len(report["days"]) == 2
    assert report["days"][-1]["date"] == "2026-08-17"


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


def test_groups_sort_by_iso_date_not_chinese_label():
    """Chinese labels like 7月8日 sort after 7月20日 lexicographically — must use ISO keys."""
    rows = [
        {"match_time": "2026-08-08T00:00:00", "stage": "第1轮", "matchday": 1},
        {"match_time": "2026-08-12T05:00:00", "stage": "第2轮", "matchday": 2},
        {"match_time": "2026-08-20T03:00:00", "stage": "第3轮", "matchday": 3},
        {"match_time": "2026-08-15T02:00:00", "stage": "第2轮", "matchday": 2},
    ]
    groups: dict[str, dict] = {}
    for row in rows:
        key, label = _backtest_group_key_label(row, prefer_date=True)
        groups[key] = {"group_key": key, "label": label, "matchday": None}
    group_list = list(groups.values())
    wrong = sorted(group_list, key=lambda x: x["label"], reverse=True)
    assert wrong[0]["group_key"] == "d2026-08-08"
    fixed = sorted(group_list, key=lambda x: x["group_key"], reverse=True)
    assert [g["group_key"] for g in fixed] == [
        "d2026-08-20",
        "d2026-08-15",
        "d2026-08-12",
        "d2026-08-08",
    ]


class _EmptyQueryResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class _EmptySession:
    async def execute(self, *args, **kwargs):
        return _EmptyQueryResult()


def test_league_notes_do_not_mention_knockout_seed():
    assert _is_worldcup_competition("premier-league") is False
    assert _is_worldcup_competition("worldcup-2026") is False
    notes = _notes_for("la-liga")
    assert notes == LEAGUE_NOTES
    assert any("不混入世界杯" in n for n in notes)


def test_league_backtest_does_not_seed_worldcup_matches():
    from service.score_backtest import compute_score_backtest

    async def _run():
        evaluated, skipped, _ = await _collect_evaluated_rows(_EmptySession(), "premier-league")
        report = await compute_score_backtest(_EmptySession(), "bundesliga")
        return evaluated, skipped, report

    evaluated, skipped, report = asyncio.run(_run())
    assert evaluated == []
    assert skipped == 0
    assert report["matches_evaluated"] == 0
    assert report["groups"] == []
    assert report["notes"] == LEAGUE_NOTES
    assert report["competition_slug"] == "bundesliga"


def test_league_expected_goals_do_not_use_fifa_team_data():
    from service.score_backtest import _expected_goals, _pipeline_ranks, LEAGUE_HOME_XG, LEAGUE_AWAY_XG

    assert _expected_goals("巴萨", "马竞", "la-liga") == (LEAGUE_HOME_XG, LEAGUE_AWAY_XG)
    assert _pipeline_ranks("巴萨", "马竞", "la-liga") == (10, 10)
    assert _expected_goals("巴萨", "马竞", "premier-league") == (LEAGUE_HOME_XG, LEAGUE_AWAY_XG)


def test_all_big_five_backtests_ignore_worldcup_history():
    from data.competitions import COMPETITIONS

    async def _run():
        out = {}
        for slug, meta in COMPETITIONS.items():
            if meta.get("type") != "club":
                continue
            evaluated, _, _ = await _collect_evaluated_rows(_EmptySession(), slug)
            out[slug] = evaluated
        return out

    by_slug = asyncio.run(_run())
    assert by_slug
    for slug, rows in by_slug.items():
        assert rows == [], slug
        nations = {r["team_a"] for r in rows} | {r["team_b"] for r in rows}
        assert "葡萄牙" not in nations
        assert "英格兰" not in nations
