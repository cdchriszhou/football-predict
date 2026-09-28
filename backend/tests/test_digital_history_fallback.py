# -*- coding: utf-8 -*-
"""Tests for digital history disk fallback when CWL is unreachable."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from service import digital_history_store as store
from service import ssq_service


def test_ssq_disk_fallback_when_live_fails(monkeypatch, tmp_path):
    draws = [
        {
            "issue": "2026112",
            "red": [1, 4, 11, 12, 17, 29],
            "blue": 11,
            "digits": [1, 4, 11, 12, 17, 29, 11],
            "result": "01 04 11 12 17 29 + 11",
            "kind": "ssq",
        }
    ]
    monkeypatch.setattr(store, "_DIR", tmp_path)
    monkeypatch.setattr(store, "_SEED_SSQ", tmp_path / "missing.json")
    store.save_last_good("ssq", draws)

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise OSError(11002, "getaddrinfo failed")

    monkeypatch.setattr(ssq_service.httpx, "AsyncClient", _FakeClient)
    ssq_service.clear_ssq_history_cache()

    out = asyncio.run(ssq_service.fetch_ssq_history(10, force_refresh=True))
    assert len(out) == 1
    assert out[0]["issue"] == "2026112"
    meta = ssq_service.get_ssq_fetch_meta()
    assert meta["source"] == "disk_fallback"
    assert meta["newest"] == "2026112"


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path)
    monkeypatch.setattr(store, "_SEED_SSQ", tmp_path / "nope.json")
    assert store.load_last_good("ssq", 5) == []
    store.save_last_good("ssq", [{"issue": "1", "red": [1, 2, 3, 4, 5, 6], "blue": 1}])
    loaded = store.load_last_good("ssq", 5)
    assert loaded[0]["issue"] == "1"
    assert (tmp_path / "ssq_last_good.json").is_file()
