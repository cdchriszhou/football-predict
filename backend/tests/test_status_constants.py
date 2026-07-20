"""Core unit tests for data integrity helpers."""
import pytest

from data.status_constants import (
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_UPCOMING,
    normalize_match_status,
    normalize_player_status,
    match_status_in_db_values,
)
from data.match_status import season_label_for


def test_season_label_for():
    assert season_label_for({"season_year": 2025}) == "2025/26"
    assert season_label_for({}) is None


def test_normalize_match_status_legacy():
    assert normalize_match_status("未开始") == MATCH_UPCOMING
    assert normalize_match_status("进行中") == MATCH_LIVE
    assert normalize_match_status("已结束") == MATCH_FINISHED


def test_normalize_match_status_canonical():
    assert normalize_match_status("upcoming") == MATCH_UPCOMING
    assert normalize_match_status(None) == MATCH_UPCOMING


def test_normalize_player_status():
    assert normalize_player_status("正常") == "active"
    assert normalize_player_status("active") == "active"


def test_match_status_in_db_values_includes_legacy():
    values = match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)
    assert MATCH_UPCOMING in values
    assert MATCH_LIVE in values
    assert "未开始" in values
    assert "进行中" in values
