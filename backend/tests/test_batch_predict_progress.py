"""Batch predict progress callbacks."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from service.prediction_service import PredictionService, _report_progress


def test_report_progress_passes_current_match():
    async def _run():
        cb = AsyncMock()
        match = SimpleNamespace(team_a="乌拉圭", team_b="佛得角")
        await _report_progress(cb, 2, 2, 0, match=match)
        cb.assert_awaited_once_with(2, 2, 0, current_match="乌拉圭 vs 佛得角")

    asyncio.run(_run())


def test_sqlite_batch_predict_reports_progress_before_each_match():
    async def _run():
        service = PredictionService()
        matches = [
            SimpleNamespace(id=1, team_a="A", team_b="B", match_time=None),
            SimpleNamespace(id=2, team_a="C", team_b="D", match_time=None),
        ]
        progress: list[tuple] = []

        async def on_progress(done, success, failed, **extra):
            progress.append((done, success, failed, extra.get("current_match")))

        class _Scalars:
            def all(self):
                return matches

        class _Result:
            def scalars(self):
                return _Scalars()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_Result())

        with patch("service.prediction_service.IS_SQLITE", True), patch.object(
            service, "predict_match", new=AsyncMock(side_effect=[{"ok": 1}, {"ok": 2}]),
        ):
            await service.batch_predict(mock_db, "rule_engine", on_progress=on_progress)

        assert progress[0] == (0, 0, 0, None)
        assert progress[1] == (0, 0, 0, "A vs B")
        assert progress[2] == (1, 1, 0, "A vs B")
        assert progress[3] == (1, 1, 0, "C vs D")
        assert progress[4] == (2, 2, 0, "C vs D")

    asyncio.run(_run())
