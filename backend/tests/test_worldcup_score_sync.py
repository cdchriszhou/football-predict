"""Tests for World Cup live score sync helpers."""
from datetime import datetime
from types import SimpleNamespace

from crawler.worldcup_score_sync import (
    _assign_external_id,
    _build_ext_index,
    _find_db_match,
    _perspective_scores,
)


def _db_row(team_a, team_b, match_time, row_id=1, external_id=None):
    return SimpleNamespace(
        id=row_id,
        team_a=team_a, team_b=team_b, match_time=match_time,
        status="upcoming", result_a=None, result_b=None, external_id=external_id,
    )


def test_find_db_match_argentina_algeria():
    db_rows = [_db_row("阿根廷", "阿尔及利亚", datetime(2026, 6, 17, 9, 0))]
    fd = {
        "home_name_en": "Argentina",
        "away_name_en": "Algeria",
        "kickoff_beijing": datetime(2026, 6, 17, 9, 0),
        "result_a": 3,
        "result_b": 0,
        "external_id": 999,
    }
    match, a_is_home = _find_db_match(db_rows, fd)
    assert match is not None
    assert a_is_home is True
    assert _perspective_scores(fd, a_is_home) == (3, 0)


def test_perspective_scores_swapped_teams():
    fd = {"result_a": 2, "result_b": 1}
    assert _perspective_scores(fd, True) == (2, 1)
    assert _perspective_scores(fd, False) == (1, 2)


def test_assign_external_id_skips_duplicate_row():
    canonical = _db_row("阿根廷", "阿尔及利亚", datetime(2026, 6, 17, 9, 0), row_id=43, external_id=537348)
    duplicate = _db_row("阿根廷", "阿尔及利亚", datetime(2026, 6, 17, 9, 0), row_id=2065)
    ext_index = _build_ext_index([canonical, duplicate])
    assert not _assign_external_id(duplicate, 537348, ext_index)
    assert canonical.external_id == 537348
    assert duplicate.external_id is None


def test_june22_history_includes_uruguay_cape_verde():
    from data.worldcup_history import HISTORICAL_MATCHES

    row = next(
        (
            m for m in HISTORICAL_MATCHES
            if m.get("year") == 2026
            and m.get("team_a") == "乌拉圭"
            and m.get("team_b") == "佛得角"
        ),
        None,
    )
    assert row is not None
    assert row["result_a"] == 2 and row["result_b"] == 2


def test_june25_history_includes_bosnia_qatar():
    from data.worldcup_history import HISTORICAL_MATCHES

    row = next(
        (
            m for m in HISTORICAL_MATCHES
            if m.get("year") == 2026
            and m.get("team_a") == "波黑"
            and m.get("team_b") == "卡塔尔"
        ),
        None,
    )
    assert row is not None
    assert row["result_a"] == 3 and row["result_b"] == 1
    assert row.get("matchday") == 3


def test_build_ext_index_clears_duplicate_owner():
    canonical = _db_row("墨西哥", "南非", datetime(2026, 6, 18, 3, 0), row_id=30, external_id=537342)
    duplicate = _db_row("南非", "墨西哥", datetime(2026, 6, 18, 3, 0), row_id=2065, external_id=537342)
    ext_index = _build_ext_index([canonical, duplicate])
    assert ext_index[537342].id == 30
    assert duplicate.external_id is None
