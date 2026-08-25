"""数字彩主推号持久化：按「基于期号」存下期预测，开奖后可对照命中。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "digital_rec_history.json"
_LOCK = threading.Lock()
_MAX_ENTRIES = 800


def _load() -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return {}
    try:
        raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 按更新时间裁剪，避免无限膨胀
    if len(data) > _MAX_ENTRIES:
        ranked = sorted(
            data.items(),
            key=lambda kv: str((kv[1] or {}).get("updated_at") or ""),
            reverse=True,
        )
        data = dict(ranked[:_MAX_ENTRIES])
    _STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _key(game_id: str, based_on_issue: str) -> str:
    return f"{game_id}:{based_on_issue}"


def save_primary_prediction(
    game_id: str,
    based_on_issue: str | None,
    recommendations: list[dict],
    *,
    rotate: int = 0,
) -> None:
    """保存当期主推（推荐 1）。仅 rotate=0，避免「换一批」覆盖主记录。"""
    if rotate or not game_id or not based_on_issue or not recommendations:
        return
    primary = recommendations[0] if recommendations else None
    if not isinstance(primary, dict):
        return
    digits = primary.get("digits")
    if not isinstance(digits, list) or not digits:
        return
    try:
        digits_i = [int(x) for x in digits]
    except (TypeError, ValueError):
        return
    display = primary.get("display") or " ".join(str(x) for x in digits_i)
    entry = {
        "game": game_id,
        "based_on_issue": str(based_on_issue),
        "digits": digits_i,
        "display": str(display),
        "source": primary.get("source") or "frequency",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _LOCK:
        data = _load()
        data[_key(game_id, str(based_on_issue))] = entry
        _save(data)


def get_stored_primary(game_id: str, based_on_issue: str | None) -> dict[str, Any] | None:
    if not game_id or not based_on_issue:
        return None
    with _LOCK:
        data = _load()
        hit = data.get(_key(game_id, str(based_on_issue)))
        return dict(hit) if isinstance(hit, dict) else None
