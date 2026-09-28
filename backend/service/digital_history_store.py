# -*- coding: utf-8 -*-
"""Last-good digital lottery history on disk — offline fallback when CWL is down."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from utils.logger import logger

_DIR = Path(__file__).resolve().parents[1] / "data" / "digital_history"
_SEED_SSQ = Path(__file__).resolve().parents[1] / "scripts" / "_ssq_history_cache.json"


def _path(game: str) -> Path:
    return _DIR / f"{game}_last_good.json"


def save_last_good(game: str, draws: list[dict[str, Any]]) -> None:
    if not draws:
        return
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "game": game,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "newest": draws[0].get("issue"),
            "count": len(draws),
            "draws": draws,
        }
        tmp = _path(game).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_path(game))
    except Exception as exc:  # noqa: BLE001
        logger.warning("digital history save failed [%s]: %s", game, exc)


def load_last_good(game: str, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 100), 100))
    path = _path(game)
    if not path.is_file() and game == "ssq" and _SEED_SSQ.is_file():
        # One-shot seed from backtest cache so local DNS outages still have data
        try:
            raw = json.loads(_SEED_SSQ.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw:
                save_last_good("ssq", raw[:100])
        except Exception as exc:  # noqa: BLE001
            logger.warning("ssq seed cache load failed: %s", exc)

    path = _path(game)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        draws = payload.get("draws") if isinstance(payload, dict) else payload
        if not isinstance(draws, list):
            return []
        out = [d for d in draws if isinstance(d, dict) and d.get("issue")]
        return out[:limit]
    except Exception as exc:  # noqa: BLE001
        logger.warning("digital history load failed [%s]: %s", game, exc)
        return []
