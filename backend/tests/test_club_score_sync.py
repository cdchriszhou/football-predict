"""Club league live/finished scores must sync from football-data, not World Cup history."""
from datetime import datetime
from types import SimpleNamespace

from crawler.club_score_sync import apply_club_fd_scores, find_club_match
from data.status_constants import MATCH_FINISHED, MATCH_LIVE, MATCH_UPCOMING


def _match(**kwargs):
    defaults = dict(
        id=1,
        competition_slug="la-liga",
        stage="第1轮",
        team_a="巴萨",
        team_b="马拉加",
        match_time=datetime(2026, 8, 15, 23, 0),
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
        status=MATCH_UPCOMING,
        external_id=90001,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_find_club_match_by_external_id():
    m = _match()
    fd = {
        "external_id": 90001,
        "home_id": None,
        "away_id": None,
        "home_name_en": "FC Barcelona",
        "away_name_en": "Malaga",
        "kickoff_beijing": datetime(2026, 8, 15, 23, 0),
        "status_raw": "FINISHED",
        "result_a": 3,
        "result_b": 0,
    }
    found, a_is_home = find_club_match([m], fd)
    assert found is m
    assert a_is_home is True


def test_apply_club_fd_scores_writes_finished_result():
    m = _match()
    fd = {
        "external_id": 90001,
        "home_id": None,
        "home_name_en": "FC Barcelona",
        "away_id": None,
        "away_name_en": "Malaga CF",
        "kickoff_beijing": datetime(2026, 8, 15, 23, 0),
        "status_raw": "FINISHED",
        "result_a": 2,
        "result_b": 1,
        "penalty_a": None,
        "penalty_b": None,
    }
    stats = apply_club_fd_scores([m], [fd])
    assert stats["updated"] == 1
    assert stats["finished"] == 1
    assert m.status == MATCH_FINISHED
    assert m.result_a == 2 and m.result_b == 1


def test_apply_club_fd_scores_writes_live_score():
    m = _match(external_id=77)
    fd = {
        "external_id": 77,
        "home_name_en": "FC Barcelona",
        "away_name_en": "Malaga",
        "home_id": None,
        "away_id": None,
        "kickoff_beijing": datetime(2026, 8, 15, 23, 0),
        "status_raw": "IN_PLAY",
        "result_a": 1,
        "result_b": 0,
        "penalty_a": None,
        "penalty_b": None,
    }
    stats = apply_club_fd_scores([m], [fd])
    assert stats["live"] == 1
    assert m.status == MATCH_LIVE
    assert m.result_a == 1 and m.result_b == 0


def test_league_live_sync_is_not_skipped_for_clubs():
    import inspect
    from data import match_status

    src = inspect.getsource(match_status.sync_live_scores)
    assert "club_score_sync" in src
