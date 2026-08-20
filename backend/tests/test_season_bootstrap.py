"""Bootstrap current-season fixtures when only old-season rows exist."""
import asyncio
from unittest.mock import AsyncMock, patch

from crawler import club_data_sync as cds


def test_ensure_current_season_skips_without_api_key():
    db = AsyncMock()

    async def _run():
        with patch.object(cds, "current_season_match_count", AsyncMock(return_value=("2026/27", 0))), \
             patch.object(cds, "_api_key", return_value=""):
            return await cds.ensure_current_season_fixtures(db, "la-liga", force=True)

    result = asyncio.run(_run())
    assert result["status"] == "skipped"
    assert result["reason"] == "no_football_data_api_key"
    assert result["season"] == "2026/27"
    assert result["matches"] == 0


def test_ensure_current_season_ok_when_fixtures_exist():
    db = AsyncMock()

    async def _run():
        with patch.object(cds, "current_season_match_count", AsyncMock(return_value=("2026/27", 12))):
            return await cds.ensure_current_season_fixtures(db, "la-liga", force=True)

    result = asyncio.run(_run())
    assert result == {"status": "ok", "season": "2026/27", "matches": 12}


def test_ensure_current_season_calls_sync_when_empty():
    db = AsyncMock()
    sync_result = {
        "status": "success",
        "source": "football-data.org",
        "season": "2026/27",
        "schedule": {"created": 10, "updated": 0},
    }

    async def _run():
        with patch.object(cds, "current_season_match_count", AsyncMock(side_effect=[
            ("2026/27", 0),
            ("2026/27", 10),
        ])), patch.object(cds, "_api_key", return_value="test-key"), \
             patch.object(cds, "sync_league_from_football_data", AsyncMock(return_value=sync_result)) as sync:
            result = await cds.ensure_current_season_fixtures(
                db, "la-liga", force=True, include_squads=False,
            )
            sync.assert_awaited_once_with(db, "la-liga", include_squads=False)
            return result

    result = asyncio.run(_run())
    assert result["status"] == "success"
    assert result["matches"] == 10


def test_club_season_filter_targets_2026_27():
    from data.competitions import get_competition
    from data.match_status import season_label_for

    assert season_label_for(get_competition("la-liga")) == "2026/27"
