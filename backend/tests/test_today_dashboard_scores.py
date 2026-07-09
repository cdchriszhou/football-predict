"""Dashboard today/recent endpoints must expose scores via history overlay."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.matches import get_recent_results, get_today_matches, match_to_dict
from data.match_status import match_has_display_score


def _match(**kwargs):
    defaults = dict(
        id=1,
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        group_name="",
        team_a="阿根廷",
        team_b="埃及",
        match_time=datetime(2026, 7, 8, 0, 0),
        location="亚特兰大",
        stadium="",
        result_a=None,
        result_b=None,
        penalty_a=None,
        penalty_b=None,
        status="finished",
        season=None,
        matchday=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_match_has_display_score_from_history():
    m = _match()
    assert match_has_display_score(m) is True


def test_match_to_dict_overlays_july8_r16():
    d = match_to_dict(_match())
    assert d["result_a"] == 3 and d["result_b"] == 2
    assert d["status"] == "finished"


def test_recent_results_includes_history_overlay_without_db_score():
    async def _run():
        m = _match(id=2100)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [m]))
        )

        with patch("api.matches._ensure_results_synced", AsyncMock()), patch(
            "api.matches._knockout_by_no", AsyncMock(return_value=None)
        ), patch("api.matches.resolve_competition", lambda x: "worldcup-2026"), patch(
            "api.matches._club_season_filter", lambda x: None
        ):
            return await get_recent_results(competition="worldcup-2026", hours=72, limit=12, db=db)

    res = asyncio.run(_run())
    assert res["code"] == 200
    assert len(res["data"]) == 1
    assert res["data"][0]["result_a"] == 3 and res["data"][0]["result_b"] == 2


def test_today_rest_day_shows_yesterday_finished():
    async def _run():
        yesterday = _match(id=2100)
        tomorrow_qf = _match(
            id=2102,
            team_a="第89场胜者",
            team_b="摩洛哥",
            stage="1/4决赛",
            match_time=datetime(2026, 7, 10, 4, 0),
            status="upcoming",
        )
        db = AsyncMock()
        calls = {"n": 0}

        def _execute(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                rows = [yesterday, tomorrow_qf]
            else:
                rows = [yesterday]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

        db.execute = AsyncMock(side_effect=_execute)

        with patch("api.matches._ensure_results_synced", AsyncMock()), patch(
            "api.matches._knockout_by_no", AsyncMock(return_value=None)
        ), patch("api.matches.resolve_competition", lambda x: "worldcup-2026"), patch(
            "api.matches._club_season_filter", lambda x: None
        ), patch("api.matches.include_in_today_dashboard", lambda m: False), patch(
            "utils.datetime_helpers.china_today", lambda: datetime(2026, 7, 9).date()
        ):
            return await get_today_matches(competition="worldcup-2026", db=db)

    res = asyncio.run(_run())
    assert res["code"] == 200
    assert len(res["data"]) == 1
    assert res["data"][0]["team_a"] == "阿根廷"
    assert res["data"][0]["result_a"] == 3
