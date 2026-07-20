"""体彩排列3 / 排列5 — 开奖拉取与基于历史频率的号码推荐。"""

from __future__ import annotations

import asyncio
import time
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

# 进程内短缓存，减轻对体彩网关压力
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 600

# 热号权重略高，冷号回补作辅助（仅供参考，非开奖预测）
_HOT_WEIGHT = 0.7
_COLD_WEIGHT = 0.3


def get_games_catalog() -> dict[str, Any]:
    return {
        "slug": "pailie",
        "title": "体彩排列3 / 排列5",
        "disclaimer": (
            "本模块仅提供玩法说明、频率统计与选号参考，不提供购彩下单；"
            "历史频率不能保证未来开奖结果，请理性投注并到官方渠道购买。"
        ),
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
    parsed: list[int] = []
    for d in digits:
        d = str(d).strip()
        if not d:
            continue
        try:
            parsed.append(int(d) % 10)
        except ValueError:
            if d.isdigit():
                parsed.append(int(d[-1]))
    need = 3 if game_id == "pl3" else 5
    if len(parsed) < need:
        return None
    parsed = parsed[:need]
    return {
        "issue": str(issue),
        "result": " ".join(str(x) for x in parsed),
        "digits": parsed,
        "draw_time": draw_time,
        "sale_amount": raw.get("totalSaleAmount") or raw.get("saleAmount"),
        "pool_balance": raw.get("poolBalanceAfterdraw") or raw.get("poolBalance"),
    }


async def _fetch_history_page(
    client: httpx.AsyncClient,
    game_id: str,
    page_no: int,
    page_size: int,
) -> list[dict]:
    game_no = _GAME_NOS.get(game_id)
    if not game_no:
        return []
    params = {
        "gameNo": game_no,
        "provinceId": "0",
        "pageSize": str(page_size),
        "isVerify": "1",
        "pageNo": str(page_no),
    }
    resp = await client.get(_HISTORY_URL, params=params)
    if resp.status_code != 200:
        logger.warning("pailie history HTTP %s for %s page %s", resp.status_code, game_id, page_no)
        return []
    payload = resp.json()
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


async def _fetch_history(game_id: str, limit: int = 100) -> list[dict]:
    limit = max(1, min(int(limit or 100), 200))
    cache_key = f"{game_id}:{limit}"
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return list(cached[1])

    page_size = min(50, limit)
    pages_needed = (limit + page_size - 1) // page_size
    collected: list[dict] = []
    seen_issues: set[str] = set()
    last_err: Exception | None = None

    for label, proxy in sporttery_proxy_attempts():
        collected = []
        seen_issues = set()
        try:
            async with httpx.AsyncClient(
                proxy=proxy,
                timeout=15.0,
                headers=_BROWSER_HEADERS,
                follow_redirects=True,
            ) as client:
                for page_no in range(1, pages_needed + 1):
                    rows = await _fetch_history_page(client, game_id, page_no, page_size)
                    if not rows:
                        break
                    for item in rows:
                        issue = item["issue"]
                        if issue in seen_issues:
                            continue
                        seen_issues.add(issue)
                        collected.append(item)
                        if len(collected) >= limit:
                            break
                    if len(collected) >= limit or len(rows) < page_size:
                        break
            if collected:
                break
        except Exception as e:
            last_err = e
            logger.warning("pailie history via %s failed [%s]: %s", label, game_id, e)
            continue

    if not collected and last_err:
        logger.warning("pailie history exhausted proxies [%s]: %s", game_id, last_err)

    _CACHE[cache_key] = (time.monotonic(), list(collected))
    return collected


async def get_draw_history(game_id: str | None = None, limit: int = 10) -> dict[str, Any]:
    games = [game_id] if game_id in ("pl3", "pl5") else ["pl3", "pl5"]
    limit = max(1, min(int(limit or 10), 50))
    results = await asyncio.gather(*[_fetch_history(g, limit) for g in games])
    history = {g: rows for g, rows in zip(games, results)}
    reachable = any(bool(v) for v in history.values())
    return {
        "reachable": reachable,
        "history": history,
        "message": None if reachable else "暂时无法获取官方开奖数据，仍可使用选号与玩法说明。",
    }


def _digit_count(n_pos: int) -> list[list[int]]:
    return [[0] * 10 for _ in range(n_pos)]


def _normalize_scores(raw: list[float]) -> list[float]:
    lo, hi = min(raw), max(raw)
    if hi - lo < 1e-9:
        return [0.5] * len(raw)
    return [(x - lo) / (hi - lo) for x in raw]


def _analyze_draws(draws: list[dict], n_pos: int) -> dict[str, Any]:
    """基于历史开奖统计各位出现率、遗漏与综合得分。"""
    freq = _digit_count(n_pos)
    overall = [0] * 10
    last_seen = [[None] * 10 for _ in range(n_pos)]
    overall_last = [None] * 10

    # draws[0] 为最近一期
    for age, row in enumerate(draws):
        digits = row.get("digits") or []
        if len(digits) < n_pos:
            continue
        for pos in range(n_pos):
            d = int(digits[pos]) % 10
            freq[pos][d] += 1
            overall[d] += 1
            if last_seen[pos][d] is None:
                last_seen[pos][d] = age
            if overall_last[d] is None:
                overall_last[d] = age

    sample = len(draws) or 1
    position_stats: list[list[dict]] = []
    position_scores: list[list[float]] = []

    for pos in range(n_pos):
        counts = freq[pos]
        rates = [c / sample for c in counts]
        gaps = [last_seen[pos][d] if last_seen[pos][d] is not None else sample for d in range(10)]
        hot_n = _normalize_scores(rates)
        cold_n = _normalize_scores([float(g) for g in gaps])
        scores = [
            _HOT_WEIGHT * hot_n[d] + _COLD_WEIGHT * cold_n[d]
            for d in range(10)
        ]
        position_scores.append(scores)
        rows = []
        for d in range(10):
            rows.append({
                "digit": d,
                "count": counts[d],
                "rate": round(rates[d], 4),
                "miss": gaps[d],
                "score": round(scores[d], 4),
                "tag": "hot" if rates[d] >= sorted(rates, reverse=True)[2] else (
                    "cold" if gaps[d] >= sorted(gaps, reverse=True)[2] else "normal"
                ),
            })
        rows.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))
        position_stats.append(rows)

    overall_rows = []
    overall_rates = [c / (sample * n_pos) for c in overall]
    overall_gaps = [overall_last[d] if overall_last[d] is not None else sample for d in range(10)]
    oh = _normalize_scores(overall_rates)
    oc = _normalize_scores([float(g) for g in overall_gaps])
    for d in range(10):
        score = _HOT_WEIGHT * oh[d] + _COLD_WEIGHT * oc[d]
        overall_rows.append({
            "digit": d,
            "count": overall[d],
            "rate": round(overall_rates[d], 4),
            "miss": overall_gaps[d],
            "score": round(score, 4),
        })
    overall_rows.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    return {
        "sample_size": sample,
        "position_stats": position_stats,
        "position_scores": position_scores,
        "overall": overall_rows,
        "hot_digits": [r["digit"] for r in overall_rows[:5]],
        "cold_digits": sorted(range(10), key=lambda d: (-overall_gaps[d], d))[:5],
    }


def _pick_direct_numbers(position_scores: list[list[float]], count: int = 5) -> list[list[int]]:
    """按位综合得分生成多注直选，尽量错开各位次选。"""
    n_pos = len(position_scores)
    ranked = [
        sorted(range(10), key=lambda d: (-scores[d], d))
        for scores in position_scores
    ]
    picks: list[list[int]] = []
    used: set[tuple[int, ...]] = set()

    # 主推：各位第 1
    primary = [ranked[p][0] for p in range(n_pos)]
    picks.append(primary)
    used.add(tuple(primary))

    # 备选：轮流用第 2、3 名替换某一位
    for rank_i in range(1, 4):
        for pos in range(n_pos):
            nums = list(primary)
            nums[pos] = ranked[pos][min(rank_i, 9)]
            key = tuple(nums)
            if key in used:
                continue
            used.add(key)
            picks.append(nums)
            if len(picks) >= count:
                return picks

    # 各位取第 2 名组合
    secondary = [ranked[p][1] for p in range(n_pos)]
    if tuple(secondary) not in used:
        picks.append(secondary)
    return picks[:count]


def _build_recommendations(game_id: str, draws: list[dict], analysis: dict[str, Any]) -> list[dict]:
    n_pos = 3 if game_id == "pl3" else 5
    scores = analysis["position_scores"]
    directs = _pick_direct_numbers(scores, count=5)
    recs: list[dict] = []

    for i, nums in enumerate(directs):
        conf = sum(scores[p][nums[p]] for p in range(n_pos)) / n_pos
        recs.append({
            "id": f"direct-{i + 1}",
            "mode": "direct",
            "label": "主推直选" if i == 0 else f"备选直选 {i}",
            "digits": nums,
            "display": " ".join(str(x) for x in nums),
            "confidence": round(conf, 4),
            "reason": "各位历史出现率 + 遗漏综合得分优选",
            "bets": 1,
        })

    if game_id == "pl3":
        hot = analysis["hot_digits"]
        # 组选3：取综合分最高的两个号（官方复式需 ≥2）
        g3 = sorted(hot[:2])
        if len(g3) >= 2:
            recs.append({
                "id": "group3-1",
                "mode": "group3",
                "label": "热号组选3",
                "digits": g3,
                "display": " ".join(str(x) for x in g3),
                "confidence": round(
                    sum(next(r["score"] for r in analysis["overall"] if r["digit"] == d) for d in g3) / 2,
                    4,
                ),
                "reason": "近期整体出现频率较高的两位号码",
                "bets": 2,
            })
        # 组选6：取热号前三
        g6 = sorted(hot[:3])
        if len(g6) >= 3:
            recs.append({
                "id": "group6-1",
                "mode": "group6",
                "label": "热号组选6",
                "digits": g6,
                "display": " ".join(str(x) for x in g6),
                "confidence": round(
                    sum(next(r["score"] for r in analysis["overall"] if r["digit"] == d) for d in g6) / 3,
                    4,
                ),
                "reason": "近期整体出现频率较高的三位号码",
                "bets": 1,
            })
        # 冷号回补直选：各位遗漏较大的号
        cold_pick = []
        for pos_stats in analysis["position_stats"]:
            by_miss = sorted(pos_stats, key=lambda x: (-x["miss"], -x["score"], x["digit"]))
            cold_pick.append(by_miss[0]["digit"])
        if tuple(cold_pick) not in {tuple(r["digits"]) for r in recs if r["mode"] == "direct"}:
            recs.append({
                "id": "cold-direct",
                "mode": "direct",
                "label": "冷号回补直选",
                "digits": cold_pick,
                "display": " ".join(str(x) for x in cold_pick),
                "confidence": round(
                    sum(scores[p][cold_pick[p]] for p in range(n_pos)) / n_pos,
                    4,
                ),
                "reason": "各位遗漏期数偏大的号码，作均衡参考",
                "bets": 1,
            })

    if game_id == "pl5":
        cold_pick = []
        for pos_stats in analysis["position_stats"]:
            by_miss = sorted(pos_stats, key=lambda x: (-x["miss"], -x["score"], x["digit"]))
            cold_pick.append(by_miss[0]["digit"])
        if tuple(cold_pick) not in {tuple(r["digits"]) for r in recs}:
            recs.append({
                "id": "cold-direct",
                "mode": "direct",
                "label": "冷号回补直选",
                "digits": cold_pick,
                "display": " ".join(str(x) for x in cold_pick),
                "confidence": round(
                    sum(scores[p][cold_pick[p]] for p in range(n_pos)) / n_pos,
                    4,
                ),
                "reason": "各位遗漏期数偏大的号码，作均衡参考",
                "bets": 1,
            })

    return recs


async def get_recommendations(
    game_id: str,
    window: int = 100,
) -> dict[str, Any]:
    if game_id not in ("pl3", "pl5"):
        return {
            "reachable": False,
            "message": "未知玩法",
            "game": game_id,
            "window": window,
            "sample_size": 0,
            "recommendations": [],
            "position_stats": [],
            "overall": [],
            "hot_digits": [],
            "cold_digits": [],
        }

    window = max(20, min(int(window or 100), 200))
    draws = await _fetch_history(game_id, window)
    if not draws:
        return {
            "reachable": False,
            "message": "暂时无法获取官方开奖数据，无法生成频率推荐。请稍后刷新。",
            "game": game_id,
            "window": window,
            "sample_size": 0,
            "recommendations": [],
            "position_stats": [],
            "overall": [],
            "hot_digits": [],
            "cold_digits": [],
            "history_preview": [],
        }

    n_pos = 3 if game_id == "pl3" else 5
    analysis = _analyze_draws(draws, n_pos)
    recs = _build_recommendations(game_id, draws, analysis)

    return {
        "reachable": True,
        "message": None,
        "game": game_id,
        "window": window,
        "sample_size": analysis["sample_size"],
        "method": {
            "hot_weight": _HOT_WEIGHT,
            "cold_weight": _COLD_WEIGHT,
            "desc": "按位统计历史出现频率（热号）与遗漏期数（冷号），加权综合后推荐号码，仅供参考。",
        },
        "disclaimer": "历史频率不代表下期必然开出，请勿作为必中依据。",
        "recommendations": recs,
        "position_stats": analysis["position_stats"],
        "overall": analysis["overall"],
        "hot_digits": analysis["hot_digits"],
        "cold_digits": analysis["cold_digits"],
        "history_preview": draws[:15],
        "latest": draws[0] if draws else None,
    }
