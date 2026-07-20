"""体彩排列3 / 排列5 — 玩法说明与开奖数据（尽力拉取官方网关）。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from utils.http_client import sporttery_proxy_attempts
from utils.logger import logger

PL3_GAME = {
    "id": "pl3",
    "name": "排列3",
    "name_en": "Permutation 3",
    "digits": 3,
    "price_per_bet": 2,
    "draw_cycle": "daily",
    "note": "开奖号码取自当期排列5开奖号码的前三位。",
    "play_types": [
        {
            "id": "direct",
            "name": "直选",
            "prize": 1040,
            "desc": "所选号码与开奖号码按位全部相同即中奖。",
        },
        {
            "id": "group3",
            "name": "组选3",
            "prize": 346,
            "desc": "开奖号码有且仅有两位相同，所选号码与开奖号码相同（顺序不限）。",
        },
        {
            "id": "group6",
            "name": "组选6",
            "prize": 173,
            "desc": "开奖号码三位各不相同，所选号码与开奖号码相同（顺序不限）。",
        },
    ],
}

PL5_GAME = {
    "id": "pl5",
    "name": "排列5",
    "name_en": "Permutation 5",
    "digits": 5,
    "price_per_bet": 2,
    "draw_cycle": "daily",
    "note": "从 00000–99999 中选取一个 5 位数投注，按位全部相同即中奖。",
    "play_types": [
        {
            "id": "direct",
            "name": "直选",
            "prize": 100000,
            "desc": "所选号码与开奖号码按位全部相同即中奖（固定奖金）。",
        },
    ],
}

_HISTORY_URL = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
_GAME_NOS = {"pl3": "35", "pl5": "350133"}
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Accept": "application/json, text/plain, */*",
}


def get_games_catalog() -> dict[str, Any]:
    return {
        "slug": "pailie",
        "title": "体彩排列3 / 排列5",
        "disclaimer": "本模块仅提供玩法说明与选号辅助，不提供购彩下单。请到官方销售渠道投注。",
        "games": [PL3_GAME, PL5_GAME],
    }


def _normalize_draw_row(raw: dict, game_id: str) -> dict[str, Any] | None:
    issue = (
        raw.get("lotteryDrawNum")
        or raw.get("lotteryDrawNumber")
        or raw.get("drawNum")
        or raw.get("issue")
    )
    result = (
        raw.get("lotteryDrawResult")
        or raw.get("lotteryUnsortDrawresult")
        or raw.get("drawResult")
        or raw.get("result")
    )
    draw_time = (
        raw.get("lotteryDrawTime")
        or raw.get("drawTime")
        or raw.get("lotterySaleEndtime")
    )
    if not issue or not result:
        return None
    digits = str(result).replace(",", " ").split()
    if game_id == "pl3" and len(digits) >= 3:
        digits = digits[:3]
    elif game_id == "pl5" and len(digits) >= 5:
        digits = digits[:5]
    return {
        "issue": str(issue),
        "result": " ".join(digits),
        "digits": digits,
        "draw_time": draw_time,
        "sale_amount": raw.get("totalSaleAmount") or raw.get("saleAmount"),
        "pool_balance": raw.get("poolBalanceAfterdraw") or raw.get("poolBalance"),
    }


async def _fetch_history(game_id: str, page_size: int = 10) -> list[dict]:
    game_no = _GAME_NOS.get(game_id)
    if not game_no:
        return []
    params = {
        "gameNo": game_no,
        "provinceId": "0",
        "pageSize": str(page_size),
        "isVerify": "1",
        "pageNo": "1",
    }
    last_err: Exception | None = None
    for label, proxy in sporttery_proxy_attempts():
        try:
            async with httpx.AsyncClient(
                proxy=proxy,
                timeout=12.0,
                headers=_BROWSER_HEADERS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(_HISTORY_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "pailie history HTTP %s via %s for %s",
                        resp.status_code, label, game_id,
                    )
                    continue
                payload = resp.json()
        except Exception as e:
            last_err = e
            logger.warning("pailie history via %s failed [%s]: %s", label, game_id, e)
            continue

        value = payload.get("value") if isinstance(payload, dict) else None
        rows = []
        if isinstance(value, dict):
            rows = value.get("list") or value.get("lotteryDrawInfo") or []
        elif isinstance(payload, dict):
            rows = payload.get("list") or []
        if not isinstance(rows, list):
            return []

        out: list[dict] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item = _normalize_draw_row(raw, game_id)
            if item:
                out.append(item)
        return out

    if last_err:
        logger.warning("pailie history exhausted proxies [%s]: %s", game_id, last_err)
    return []


async def get_draw_history(game_id: str | None = None, limit: int = 10) -> dict[str, Any]:
    games = [game_id] if game_id in ("pl3", "pl5") else ["pl3", "pl5"]
    limit = max(1, min(int(limit or 10), 30))
    results = await asyncio.gather(*[_fetch_history(g, limit) for g in games])
    history = {g: rows for g, rows in zip(games, results)}
    reachable = any(bool(v) for v in history.values())
    return {
        "reachable": reachable,
        "history": history,
        "message": None if reachable else "暂时无法获取官方开奖数据，仍可使用选号与玩法说明。",
    }
