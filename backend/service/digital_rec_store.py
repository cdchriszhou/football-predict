"""数字彩推荐号持久化：按「基于期号」存下期最多 5 注，开奖后可对照命中。"""

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


def _normalize_picks(recommendations: list[dict]) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    for rec in recommendations[:5]:
        if not isinstance(rec, dict):
            continue
        digits = rec.get("digits")
        if not isinstance(digits, list) or not digits:
            continue
        try:
            digits_i = [int(x) for x in digits]
        except (TypeError, ValueError):
            continue
        picks.append({
            "digits": digits_i,
            "display": str(rec.get("display") or " ".join(str(x) for x in digits_i)),
            "source": rec.get("source") or "frequency",
        })
    return picks


def save_primary_prediction(
    game_id: str,
    based_on_issue: str | None,
    recommendations: list[dict],
    *,
    rotate: int = 0,
) -> None:
    """保存当期全部推荐（最多 5 注）。仅 rotate=0，避免「换一批」覆盖主记录。"""
    if rotate or not game_id or not based_on_issue or not recommendations:
        return
    picks = _normalize_picks(recommendations)
    if not picks:
        return
    entry = {
        "game": game_id,
        "based_on_issue": str(based_on_issue),
        "picks": picks,
        # 兼容旧字段：主推 = 第一注
        "digits": picks[0]["digits"],
        "display": picks[0]["display"],
        "source": picks[0].get("source") or "frequency",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _LOCK:
        data = _load()
        data[_key(game_id, str(based_on_issue))] = entry
        _save(data)


def get_stored_picks(game_id: str, based_on_issue: str | None) -> list[dict[str, Any]]:
    """返回已存预测列表；兼容旧版仅存主推 digits 的记录。"""
    if not game_id or not based_on_issue:
        return []
    with _LOCK:
        data = _load()
        hit = data.get(_key(game_id, str(based_on_issue)))
    if not isinstance(hit, dict):
        return []
    picks = hit.get("picks")
    if isinstance(picks, list) and picks:
        out: list[dict[str, Any]] = []
        for p in picks[:5]:
            if not isinstance(p, dict):
                continue
            digits = p.get("digits")
            if not isinstance(digits, list):
                continue
            try:
                digits_i = [int(x) for x in digits]
            except (TypeError, ValueError):
                continue
            if not digits_i:
                continue
            out.append({
                "digits": digits_i,
                "display": str(p.get("display") or " ".join(str(x) for x in digits_i)),
                "source": p.get("source") or hit.get("source") or "frequency",
            })
        if out:
            return out
    digits = hit.get("digits")
    if isinstance(digits, list) and digits:
        try:
            digits_i = [int(x) for x in digits]
        except (TypeError, ValueError):
            return []
        if digits_i:
            return [{
                "digits": digits_i,
                "display": str(hit.get("display") or " ".join(str(x) for x in digits_i)),
                "source": hit.get("source") or "frequency",
            }]
    return []


def get_stored_primary(game_id: str, based_on_issue: str | None) -> dict[str, Any] | None:
    picks = get_stored_picks(game_id, based_on_issue)
    return picks[0] if picks else None
