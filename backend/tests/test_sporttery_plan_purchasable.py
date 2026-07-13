"""Tests for sporttery plan sale-window helpers."""
from datetime import date, datetime

from service.sporttery_plan_service import (
    _is_purchasable_today,
    _is_upcoming_on_sale,
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
    assert _is_purchasable_today(st, date(2026, 7, 14)) is True
    assert _is_purchasable_today(st, date(2026, 7, 15)) is True
    assert _is_purchasable_today(st, date(2026, 7, 13)) is False


def test_upcoming_before_sale_date():
    st = _st(sale_date="2026-07-14", kickoff=datetime(2026, 7, 15, 3, 0))
    assert _is_upcoming_on_sale(st, date(2026, 7, 13)) is True
    assert _is_upcoming_on_sale(st, date(2026, 7, 14)) is False


def test_stopped_sell_status():
    st = _st(sale_date="2026-07-14", kickoff=datetime(2026, 7, 15, 3, 0), sell_status="0")
    assert _is_purchasable_today(st, date(2026, 7, 14)) is False
