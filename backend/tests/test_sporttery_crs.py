"""CRS (比分) odds parsing — sporttery.cn official key table."""
import pytest

from crawler.sporttery_client import (
    _parse_crs_key,
    _parse_crs_odds,
    normalize_score_line,
    to_db_odds,
)

# Friday004 美国 vs 巴拉圭 — live API snapshot 2026-06-12
USA_PARAGUAY_CRS = {
    "s01s00": "6.00",
    "s02s00": "5.80",
    "s02s01": "4.75",
    "s01s02": "16.00",
    "s00s01": "10.50",
    "s00s00": "8.25",
    "s1sh": "150.0",
    "s1sd": "400.0",
    "s1sa": "300.0",
    "updateDate": "2026-06-12",
    "updateTime": "19:23:53",
}


def test_parse_crs_key_official_scores():
    assert _parse_crs_key("s02s00") == (2, 0)
    assert _parse_crs_key("s01s02") == (1, 2)
    assert _parse_crs_key("s05s02") == (5, 2)
    assert _parse_crs_key("s1sh") is None
    assert _parse_crs_key("s1sd") is None


def test_parse_crs_odds_usa_paraguay_home_perspective():
    scores = _parse_crs_odds(USA_PARAGUAY_CRS, team_a_is_home=True)
    assert scores["2:0"] == 5.80
    assert scores["1:0"] == 6.00
    assert scores["1:2"] == 16.00
    assert scores["2:1"] == 4.75
    assert scores["0:1"] == 10.50
    assert scores["胜其它"] == 150.0


def test_parse_crs_odds_swapped_team_a_away():
    scores = _parse_crs_odds(USA_PARAGUAY_CRS, team_a_is_home=False)
    assert scores["0:2"] == 5.80
    assert scores["2:1"] == 16.00


def test_to_db_odds_usa_paraguay():
    st = {
        "home_team": "美国",
        "away_team": "巴拉圭",
        "had": {"h": "1.79", "d": "3.25", "a": "3.80"},
        "hhad": {"goalLine": "-1", "h": "4.02", "d": "3.08", "a": "1.80"},
        "crs": USA_PARAGUAY_CRS,
        "hafu": {},
        "ttg": {},
        "sporttery_match_id": 2040165,
        "match_num": "周五004",
    }
    row = to_db_odds(st, "美国", "巴拉圭")
    assert row is not None
    assert row["score_odds"]["2:0"] == 5.80
    assert row["score_odds"]["1:2"] == 16.00
    assert row["win_win"] == 1.79


def test_to_db_odds_crs_only_without_spf():
    """Some fixtures sell CRS before HAD/SPF — plan must still show score picks."""
    st = {
        "home_team": "卡塔尔",
        "away_team": "瑞士",
        "had": {},
        "hhad": {},
        "crs": {
            "s00s02": "3.80",
            "s00s03": "5.40",
            "s01s02": "7.20",
            "s00s00": "20.00",
            "updateDate": "2026-06-13",
            "updateTime": "12:47:23",
        },
        "hafu": {},
        "ttg": {},
        "sporttery_match_id": 2040999,
        "match_num": "周六005",
    }
    row = to_db_odds(st, "卡塔尔", "瑞士")
    assert row is not None
    assert row["win_win"] is None
    assert row["score_odds"]["0:2"] == 3.80
    assert row["score_odds"]["0:3"] == 5.40


def test_to_db_odds_hhad_and_crs_without_spf():
    """Germany-style lopsided fixtures may sell handicap + CRS before SPF."""
    st = {
        "home_team": "德国",
        "away_team": "库拉索",
        "had": {},
        "hhad": {
            "goalLine": "-3",
            "h": "1.65",
            "d": "4.85",
            "a": "3.15",
            "updateDate": "2026-06-14",
            "updateTime": "22:49:05",
        },
        "crs": {
            "s02s00": "5.50",
            "s03s00": "4.20",
            "s00s00": "60.00",
            "updateDate": "2026-06-14",
            "updateTime": "22:49:05",
        },
        "hafu": {},
        "ttg": {},
        "sporttery_match_id": 2041001,
        "match_num": "周日009",
    }
    row = to_db_odds(st, "德国", "库拉索")
    assert row is not None
    assert row["win_win"] is None
    assert row["handicap"] == "-3"
    assert row["handicap_win"] == 1.65
    assert row["score_odds"]["2:0"] == 5.50
