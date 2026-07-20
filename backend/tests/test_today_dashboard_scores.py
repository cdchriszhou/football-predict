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
            "api.matches._ensure_knockout_display_ready", AsyncMock()
        ), patch(
            "api.matches._knockout_by_no", AsyncMock(return_value=None)
        ), patch("api.matches.resolve_competition", lambda x: "worldcup-2026"), patch(
            "api.matches._club_season_filter", lambda x: None
        ):
            return await get_recent_results(competition="worldcup-2026", hours=72, limit=12, db=db)

    res = asyncio.run(_run())
    assert res["code"] == 200
    assert len(res["data"]) == 1
    assert res["data"][0]["result_a"] == 3 and res["data"][0]["result_b"] == 2


def test_today_rest_day_shows_latest_finished_matchday():
    async def _run():
        finished = _match(id=2100)
        upcoming_qf = _match(
            id=2102,
            team_a="第89场胜者",
            team_b="摩洛哥",
            stage="1/4决赛",
            match_time=datetime(2026, 7, 10, 4, 0),
            status="upcoming",
            result_a=None,
            result_b=None,
        )
        db = AsyncMock()

        def _execute(stmt):
            # Any select under rest-day lookback / primary window gets fixtures.
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [finished, upcoming_qf])
            )

        db.execute = AsyncMock(side_effect=_execute)

        with patch("api.matches._ensure_results_synced", AsyncMock()), patch(
            "api.matches._ensure_knockout_display_ready", AsyncMock()
        ), patch(
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


def test_recent_results_dedupes_same_display_pair():
    async def _run():
        a = _match(id=2104, team_a="挪威", team_b="英格兰", stage="1/4决赛",
                   match_time=datetime(2026, 7, 12, 5, 0), result_a=1, result_b=2)
        b = _match(id=2999, team_a="第91场胜者", team_b="第92场胜者", stage="1/4决赛",
                   match_time=datetime(2026, 7, 12, 5, 0), result_a=1, result_b=2)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [a, b]))
        )

        # display_teams maps placeholder → 挪威/英格兰 when by_no empty via history
        with patch("api.matches._ensure_results_synced", AsyncMock()), patch(
            "api.matches._ensure_knockout_display_ready", AsyncMock()
        ), patch(
            "api.matches._knockout_by_no", AsyncMock(return_value=None)
        ), patch(
            "api.matches.match_to_dict",
            side_effect=lambda m, knockout_by_no=None: {
                "id": m.id,
                "stage": m.stage,
                "team_a": "挪威",
                "team_b": "英格兰",
                "result_a": 1,
                "result_b": 2,
                "match_time": "2026-07-12T05:00:00+08:00",
            },
        ), patch("api.matches.resolve_competition", lambda x: "worldcup-2026"), patch(
            "api.matches._club_season_filter", lambda x: None
        ):
            return await get_recent_results(competition="worldcup-2026", hours=72, limit=12, db=db)

    res = asyncio.run(_run())
    assert res["code"] == 200
    assert len(res["data"]) == 1
    assert res["data"][0]["id"] == 2104