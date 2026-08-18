"""Tests for sporttery plan sale-window helpers."""
from datetime import date, datetime

from service.sporttery_plan_service import (
    _is_purchasable_today,
    _is_upcoming_on_sale,
    _parse_llm_score_refs,
    _prediction_has_llm,
)


def _st(*, sale_date: str, kickoff: datetime, sell_status: str = "2") -> dict:
    return {
        "sale_date": sale_date,
        "kickoff": kickoff,
        "sell_status": sell_status,
        "home_team": "A",
        "away_team": "B",
    }


def test_purchasable_from_sale_date_through_kickoff_day():
    st = _st(sale_date="2026-07-14", kickoff=datetime(2026, 7, 15, 3, 0))
    now = datetime(2026, 7, 14, 12, 0)
    assert _is_purchasable_today(st, date(2026, 7, 14), now=now) is True
    assert _is_purchasable_today(st, date(2026, 7, 15), now=now) is True
    assert _is_purchasable_today(st, date(2026, 7, 13), now=now) is False


def test_upcoming_before_sale_date():
    st = _st(sale_date="2026-07-14", kickoff=datetime(2026, 7, 15, 3, 0))
    now = datetime(2026, 7, 13, 12, 0)
    assert _is_upcoming_on_sale(st, date(2026, 7, 13), now=now) is True
    assert _is_upcoming_on_sale(st, date(2026, 7, 14), now=now) is False


def test_stopped_sell_status():
    st = _st(sale_date="2026-07-14", kickoff=datetime(2026, 7, 15, 3, 0), sell_status="0")
    assert _is_purchasable_today(st, date(2026, 7, 14)) is False


def test_la_liga_hint_matches_sporttery_league_label():
    from service.sporttery_plan_service import _is_competition_league
    from data.competitions import league_hints_for

    hints = league_hints_for("la-liga")
    assert _is_competition_league("西甲", hints)
    assert _is_competition_league("西班牙甲级联赛", hints)


def test_club_aliases_map_promoted_2026_27_names():
    from crawler.sporttery_client import normalize_team_name

    assert normalize_team_name("桑坦德") == "桑坦德竞技"
    assert normalize_team_name("拉科") == "拉科鲁尼亚"
    assert normalize_team_name("考文垂城") == "考文垂"
    assert normalize_team_name("利兹") == "利兹联"


def test_parse_llm_score_refs():
    reason = (
        "[deepseek] 首选比分2:1、1:0 | [glm] 看好1:1平局 | [qwen] 次选2:0"
    )
    refs = _parse_llm_score_refs(reason)
    assert len(refs) == 3
    assert refs[0]["model"] == "DeepSeek"
    assert refs[0]["scores"][:2] == ["2:1", "1:0"]
    assert refs[1]["scores"][0] == "1:1"


def test_prediction_has_llm():
    class P:
        model_used = "DeepSeek+GLM"
    class R:
        model_used = "rule_engine_calibrated"
    assert _prediction_has_llm(P()) is True
    assert _prediction_has_llm(R()) is False
