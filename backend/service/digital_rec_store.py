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


def _ints(values: Any) -> list[int] | None:
    if not isinstance(values, list) or not values:
        return None
    try:
        return [int(x) for x in values]
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_from_rec(rec: dict) -> dict[str, Any] | None:
    """从推荐对象抽出可持久化/回放的一注（含单式、复式、胆拖）。"""
    if not isinstance(rec, dict):
        return None
    mode = str(rec.get("mode") or "").strip() or None
    red = _ints(rec.get("red"))
    dan = _ints(rec.get("dan"))
    tuo = _ints(rec.get("tuo"))
    blue = _optional_int(rec.get("blue"))
    digits = _ints(rec.get("digits"))

    # 复式：以完整 7 红 + 蓝作为对照号码（不是样例单式 6+1）
    if mode == "fushi":
        if not red or blue is None:
            return None
        digits = list(red) + [blue]
    # 胆拖：胆 + 拖 + 蓝，便于开奖后逐球对照
    elif mode == "dantuo":
        if not dan or not tuo or blue is None:
            return None
        digits = list(dan) + list(tuo) + [blue]
    elif not digits:
        return None

    pick: dict[str, Any] = {
        "digits": digits,
        "display": str(rec.get("display") or " ".join(str(x) for x in digits)),
        "source": rec.get("source") or "frequency",
    }
    if mode:
        pick["mode"] = mode
    if red:
        pick["red"] = red
    if dan:
        pick["dan"] = dan
    if tuo:
        pick["tuo"] = tuo
    if blue is not None:
        pick["blue"] = blue
    label = rec.get("label")
    if label:
        pick["label"] = str(label)
    bets = rec.get("bets")
    if bets is not None:
        try:
            pick["bets"] = int(bets)
        except (TypeError, ValueError):
            pass
    amount = rec.get("amount")
    if amount is not None:
        try:
            pick["amount"] = int(amount)
        except (TypeError, ValueError):
            pass
    return pick


def _normalize_picks(recommendations: list[dict]) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    for rec in recommendations[:5]:
        pick = _pick_from_rec(rec)
        if pick:
            picks.append(pick)
    return picks


def save_primary_prediction(
    game_id: str,
    based_on_issue: str | None,
    recommendations: list[dict],
    *,
    rotate: int = 0,
) -> None:
    """保存当期全部推荐（最多 5 注，含复式/胆拖）。仅 rotate=0，避免「换一批」覆盖主记录。"""
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
            # 旧记录可能缺 mode/red/dan；用 _pick_from_rec 统一补齐 digits
            pick = _pick_from_rec(p)
            if not pick:
                digits = _ints(p.get("digits"))
                if not digits:
                    continue
                pick = {
                    "digits": digits,
                    "display": str(p.get("display") or " ".join(str(x) for x in digits)),
                    "source": p.get("source") or hit.get("source") or "frequency",
                }
            else:
                pick["source"] = pick.get("source") or hit.get("source") or "frequency"
            out.append(pick)
        if out:
            return out
    digits = _ints(hit.get("digits"))
    if digits:
        return [{
            "digits": digits,
            "display": str(hit.get("display") or " ".join(str(x) for x in digits)),
            "source": hit.get("source") or "frequency",
        }]
    return []


def get_stored_primary(game_id: str, based_on_issue: str | None) -> dict[str, Any] | None:
    picks = get_stored_picks(game_id, based_on_issue)
    return picks[0] if picks else None
