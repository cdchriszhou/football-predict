# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
from types import SimpleNamespace

from data import match_status as ms
from data.status_constants import MATCH_FINISHED, MATCH_UPCOMING


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.flushed = False

    async def execute(self, _stmt):
        return _FakeResult(self.rows)


def test_reopen_clears_scores_on_future_finished(monkeypatch):
    future = datetime(2027, 4, 4, 8, 0, 0)
    m = SimpleNamespace(
        competition_slug="la-liga",
        status=MATCH_FINISHED,
        match_time=future,
        result_a=1,
        result_b=2,
    )
    monkeypatch.setattr(ms, "china_now", lambda: datetime(2026, 9, 28, 14, 0, 0))
    monkeypatch.setattr(ms, "effective_kickoff_naive", lambda match: match.match_time)

    async def _flush(_db):
        _db.flushed = True

    monkeypatch.setattr(ms, "flush_session", _flush)
    db = _FakeDB([m])
    n = asyncio.run(ms.reopen_prematurely_finished_matches(db, "la-liga"))
    assert n == 1
    assert m.status == MATCH_UPCOMING
    assert m.result_a is None and m.result_b is None
    assert db.flushed


def test_reopen_keeps_legitimately_finished(monkeypatch):
    past = datetime(2026, 9, 21, 3, 0, 0)
    m = SimpleNamespace(
        competition_slug="la-liga",
        status=MATCH_FINISHED,
        match_time=past,
        result_a=1,
        result_b=0,
    )
    monkeypatch.setattr(ms, "china_now", lambda: datetime(2026, 9, 28, 14, 0, 0))
    monkeypatch.setattr(ms, "effective_kickoff_naive", lambda match: match.match_time)

    async def _flush(_db):
        _db.flushed = True

    monkeypatch.setattr(ms, "flush_session", _flush)
    db = _FakeDB([m])
    n = asyncio.run(ms.reopen_prematurely_finished_matches(db, "la-liga"))
    assert n == 0
    assert m.status == MATCH_FINISHED
    assert m.result_a == 1
    assert not db.flushed
