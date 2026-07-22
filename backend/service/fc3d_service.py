"""福利彩票 3D — 开奖拉取（推荐逻辑复用排列类按位频率引擎）。"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from utils.http_client import get_crawler_proxy
from utils.logger import logger

FC3D_GAME = {
    "id": "fc3d",
    "name": "福彩3D",
    "name_en": "Welfare 3D",
    "digits": 3,
    "alphabets": [10, 10, 10],
    "price_per_bet": 2,
    "draw_cycle": "daily",
    "note": "从 000–999 中选取一个 3 位数投注；支持直选、组选3、组选6；每日开奖。",
    "play_types": [
        {"id": "direct", "name": "直选", "prize": 1040, "desc": "所选号码与开奖号码按位全部相同即中奖。"},
        {"id": "group3", "name": "组选3", "prize": 346, "desc": "开奖号码有且仅有两位相同，所选号码与开奖号码相同（顺序不限）。"},
        {"id": "group6", "name": "组选6", "prize": 173, "desc": "开奖号码三位各不相同，所选号码与开奖号码相同（顺序不限）。"},
    ],
}

_FC3D_URLS = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
    "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice",
)
_FC3D_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.cwl.gov.cn/kjxx/3d/",
    "Accept": "application/json, text/plain, */*",
}

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 600


def clear_fc3d_history_cache() -> None:
    _CACHE.clear()


def _parse_money(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "").replace("￥", "").replace("¥", "").replace("元", "")
    if not text or text in ("-", "—", "null", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        m = re.search(r"[\d.]+", text)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None


def _format_money(val: float | None) -> str | None:
    if val is None:
        return None
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val)):,}"
    return f"{val:,.2f}"


def _normalize_fc3d_row(raw: dict) -> dict[str, Any] | None:
    """福彩 3D：red 常为 '8,6,5' 三位；无蓝球。"""
    issue = raw.get("code") or raw.get("issue") or raw.get("lotteryDrawNum")
    red_raw = raw.get("red") or raw.get("redBall") or raw.get("lotteryDrawResult") or ""
    draw_time = raw.get("date") or raw.get("lotteryDrawTime") or raw.get("drawTime")
    if not issue:
        return None

    digits: list[int] = []
    text = str(red_raw).replace("+", " ").replace("|", " ").replace("-", " ")
    tokens = [t for t in re.split(r"[,，\s]+", text.strip()) if t]

    # 紧凑三位如 "702"
    if len(tokens) == 1 and tokens[0].isdigit() and len(tokens[0]) == 3:
        digits = [int(ch) for ch in tokens[0]]
    else:
        for tok in tokens:
            try:
                n = int(tok)
            except ValueError:
                continue
            if 0 <= n <= 9:
                digits.append(n)
            if len(digits) >= 3:
                break

    if len(digits) == 1 and digits[0] >= 100:
        compact = f"{digits[0]:03d}"[-3:]
        digits = [int(ch) for ch in compact]

    if len(digits) != 3:
        return None

    pool = _parse_money(raw.get("poolmoney") or raw.get("poolMoney") or raw.get("pool_balance"))
    sale = _parse_money(raw.get("sales") or raw.get("saleAmount") or raw.get("totalSaleAmount"))

    return {
        "issue": str(issue),
        "result": " ".join(str(x) for x in digits),
        "digits": digits,
        "draw_time": draw_time,
        "sale_amount": sale,
        "sale_amount_text": _format_money(sale),
        "pool_balance": pool,
        "pool_balance_text": _format_money(pool),
        "prize_levels": [],
        "has_floating_pool": False,
        "kind": "fc3d",
    }


async def fetch_fc3d_history(limit: int = 100, *, force_refresh: bool = False) -> list[dict]:
    limit = max(1, min(int(limit or 100), 100))
    cache_key = f"fc3d:{limit}"
    now = time.monotonic()
    if not force_refresh:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SEC:
            return list(cached[1])
    elif cache_key in _CACHE:
        _CACHE.pop(cache_key, None)

    params = {
        "name": "3d",
        "issueCount": str(limit),
        "issueStart": "",
        "issueEnd": "",
        "dayStart": "",
        "dayEnd": "",
        "pageNo": "1",
        "pageSize": str(min(limit, 30)),
        "systemType": "PC",
    }
    proxies = [None]
    crawler = get_crawler_proxy()
    if crawler:
        proxies.append(crawler)

    collected: list[dict] = []
    for url in _FC3D_URLS:
        for proxy in proxies:
            try:
                async with httpx.AsyncClient(
                    proxy=proxy,
                    timeout=15.0,
                    headers=_FC3D_HEADERS,
                    follow_redirects=True,
                ) as client:
                    page_size = min(30, limit)
                    pages = (limit + page_size - 1) // page_size
                    seen: set[str] = set()
                    rows_all: list[dict] = []
                    for page in range(1, pages + 1):
                        p = dict(params)
                        p["pageNo"] = str(page)
                        p["pageSize"] = str(page_size)
                        resp = await client.get(url, params=p)
                        if resp.status_code != 200:
                            logger.warning("fc3d history HTTP %s via %s page %s", resp.status_code, url, page)
                            break
                        payload = resp.json()
                        result = payload.get("result") if isinstance(payload, dict) else None
                        if not isinstance(result, list):
                            result = payload.get("data") if isinstance(payload, dict) else None
                        if not isinstance(result, list) or not result:
                            break
                        for raw in result:
                            if not isinstance(raw, dict):
                                continue
                            item = _normalize_fc3d_row(raw)
                            if not item or item["issue"] in seen:
                                continue
                            seen.add(item["issue"])
                            rows_all.append(item)
                            if len(rows_all) >= limit:
                                break
                        if len(rows_all) >= limit or len(result) < page_size:
                            break
                    if rows_all:
                        collected = rows_all
                        break
            except Exception as e:
                logger.warning("fc3d history failed [%s]: %s", url, e)
                continue
        if collected:
            break

    _CACHE[cache_key] = (time.monotonic(), list(collected))
    return collected
