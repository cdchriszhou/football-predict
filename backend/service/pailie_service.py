"""体彩排列3 / 排列5 / 七星彩 — 开奖拉取、频率推荐与可选 AI 精选。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx

from utils.http_client import sporttery_proxy_attempts
from utils.logger import logger
from service.ssq_service import SSQ_GAME, fetch_ssq_history, get_ssq_recommendations
from service.dlt_service import DLT_GAME, fetch_dlt_history, get_dlt_recommendations

# ---------------------------------------------------------------------------
# Game specs
# ---------------------------------------------------------------------------

PL3_GAME = {
    "id": "pl3",
    "name": "排列3",
    "name_en": "Permutation 3",
    "digits": 3,
    "alphabets": [10, 10, 10],
    "price_per_bet": 2,
    "draw_cycle": "daily",
    "note": "开奖号码取自当期排列5开奖号码的前三位。",
    "play_types": [
        {"id": "direct", "name": "直选", "prize": 1040, "desc": "所选号码与开奖号码按位全部相同即中奖。"},
        {"id": "group3", "name": "组选3", "prize": 346, "desc": "开奖号码有且仅有两位相同，所选号码与开奖号码相同（顺序不限）。"},
        {"id": "group6", "name": "组选6", "prize": 173, "desc": "开奖号码三位各不相同，所选号码与开奖号码相同（顺序不限）。"},
    ],
}

PL5_GAME = {
    "id": "pl5",
    "name": "排列5",
    "name_en": "Permutation 5",
    "digits": 5,
    "alphabets": [10, 10, 10, 10, 10],
    "price_per_bet": 2,
    "draw_cycle": "daily",
    "note": "从 00000–99999 中选取一个 5 位数投注，按位全部相同即中奖。",
    "play_types": [
        {"id": "direct", "name": "直选", "prize": 100000, "desc": "所选号码与开奖号码按位全部相同即中奖（固定奖金）。"},
    ],
}

QXC_GAME = {
    "id": "qxc",
    "name": "七星彩",
    "name_en": "7 Star Lottery",
    "digits": 7,
    "alphabets": [10, 10, 10, 10, 10, 10, 15],
    "price_per_bet": 2,
    "draw_cycle": "tue_fri_sun",
    "note": "前6位各选 0–9，第7位（后区）选 0–14；每周二、五、日开奖。",
    "play_types": [
        {
            "id": "direct",
            "name": "单式投注",
            "prize": None,
            "prize_label": "一等奖浮动（最高500万）",
            "desc": "7位全部按位相同中一等奖；前6位相同中二等奖；另有三至六等奖固定奖金。",
        },
    ],
}

GAME_SPECS: dict[str, dict] = {
    "pl3": PL3_GAME,
    "pl5": PL5_GAME,
    "qxc": QXC_GAME,
    "ssq": SSQ_GAME,
    "dlt": DLT_GAME,
}
_HISTORY_URL = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
# 体彩网关 gameNo；七星彩常见为 04，失败时再试备选
_GAME_NOS: dict[str, tuple[str, ...]] = {
    "pl3": ("35",),
    "pl5": ("350133",),
    "qxc": ("04", "10001", "52"),
}
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Accept": "application/json, text/plain, */*",
}

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 600

_HOT_WEIGHT = 0.65
_COLD_WEIGHT = 0.25
_TREND_WEIGHT = 0.10  # 近窗相对全样本的趋势加成


def get_games_catalog() -> dict[str, Any]:
    return {
        "slug": "pailie",
        "title": "排列3 / 排列5 / 七星彩 / 双色球 / 大乐透",
        "disclaimer": (
            "本模块仅提供玩法说明、历史频率统计、概率参考与 AI 选号辅助，不提供购彩下单；"
            "历史频率与 AI 建议均不能保证未来开奖结果，请理性投注并到官方渠道购买。"
        ),
        "games": [PL3_GAME, PL5_GAME, QXC_GAME, SSQ_GAME, DLT_GAME],
    }


def _parse_digit_token(tok: str, max_val: int) -> int | None:
    tok = str(tok).strip()
    if not tok:
        return None
    try:
        n = int(tok)
    except ValueError:
        m = re.search(r"\d+", tok)
        if not m:
            return None
        n = int(m.group(0))
    if 0 <= n <= max_val:
        return n
    return None


def _parse_money(raw: Any) -> float | None:
    """Parse amounts like '174,321,661.80' / 174321661.8 / '0'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text or text in ("-", "—", "null", "None"):
        return None
    text = text.replace(",", "").replace("￥", "").replace("¥", "").replace("元", "").strip()
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


def _parse_prize_levels(raw_list: Any) -> list[dict]:
    if not isinstance(raw_list, list):
        return []
    out = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        level = item.get("prizeLevel") or item.get("prize_level") or item.get("level")
        stake_amount = _parse_money(item.get("stakeAmount") or item.get("stake_amount"))
        stake_count = item.get("stakeCount") or item.get("stake_count")
        total_prize = _parse_money(item.get("totalPrizeAmount") or item.get("total_prize_amount"))
        try:
            stake_count_n = int(str(stake_count).replace(",", "")) if stake_count not in (None, "") else None
        except ValueError:
            stake_count_n = None
        out.append({
            "level": level,
            "stake_amount": stake_amount,
            "stake_amount_text": _format_money(stake_amount),
            "stake_count": stake_count_n,
            "total_prize": total_prize,
            "total_prize_text": _format_money(total_prize),
        })
    return out


def _normalize_draw_row(raw: dict, game_id: str) -> dict[str, Any] | None:
    spec = GAME_SPECS.get(game_id)
    if not spec:
        return None
    alphabets = spec["alphabets"]
    need = len(alphabets)

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
    if not issue or result is None:
        return None

    text = str(result).replace("+", " ").replace(",", " ").replace("|", " ").replace("-", " ")
    tokens = [t for t in text.split() if t]
    if len(tokens) == 1 and tokens[0].isdigit() and len(tokens[0]) >= need:
        compact = tokens[0]
        if game_id == "qxc" and len(compact) >= 7:
            front = compact[:6]
            back = compact[6:]
            tokens = list(front) + [back]
        elif len(compact) >= need:
            tokens = list(compact[:need])

    parsed: list[int] = []
    for tok in tokens:
        if len(parsed) >= need:
            break
        max_val = alphabets[len(parsed)] - 1
        n = _parse_digit_token(tok, max_val)
        if n is None and game_id == "qxc" and len(parsed) == 6 and tok.isdigit() and len(tok) == 2:
            n = _parse_digit_token(tok, 14)
        if n is None:
            continue
        parsed.append(n)

    if len(parsed) < need:
        return None

    pool = _parse_money(
        raw.get("poolBalanceAfterdraw")
        or raw.get("poolBalanceAfterDraw")
        or raw.get("pool_balance_afterdraw")
        or raw.get("poolBalance")
        or raw.get("pool_balance")
    )
    sale = _parse_money(
        raw.get("totalSaleAmount")
        or raw.get("total_sale_amount")
        or raw.get("saleAmount")
        or raw.get("sale_amount")
    )
    prize_levels = _parse_prize_levels(
        raw.get("prizeLevelList") or raw.get("prize_level_list") or raw.get("prizeLevels")
    )

    return {
        "issue": str(issue),
        "result": " ".join(str(x) for x in parsed),
        "digits": parsed,
        "draw_time": draw_time,
        "sale_amount": sale,
        "sale_amount_text": _format_money(sale),
        "pool_balance": pool,
        "pool_balance_text": _format_money(pool),
        "prize_levels": prize_levels,
        "has_floating_pool": game_id in ("pl5", "qxc"),
    }


async def _fetch_history_page(
    client: httpx.AsyncClient,
    game_no: str,
    game_id: str,
    page_no: int,
    page_size: int,
) -> list[dict]:
    params = {
        "gameNo": game_no,
        "provinceId": "0",
        "pageSize": str(page_size),
        "isVerify": "1",
        "pageNo": str(page_no),
    }
    resp = await client.get(_HISTORY_URL, params=params)
    if resp.status_code != 200:
        logger.warning("digital history HTTP %s for %s/%s page %s", resp.status_code, game_id, game_no, page_no)
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
    if game_id not in GAME_SPECS:
        return []
    if game_id == "ssq":
        return await fetch_ssq_history(min(int(limit or 100), 100))
    if game_id == "dlt":
        return await fetch_dlt_history(min(int(limit or 100), 100))

    limit = max(1, min(int(limit or 100), 200))
    cache_key = f"{game_id}:{limit}"
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return list(cached[1])

    page_size = min(50, limit)
    pages_needed = (limit + page_size - 1) // page_size
    collected: list[dict] = []
    last_err: Exception | None = None

    for game_no in _GAME_NOS.get(game_id, ()):
        for label, proxy in sporttery_proxy_attempts():
            collected = []
            seen_issues: set[str] = set()
            try:
                async with httpx.AsyncClient(
                    proxy=proxy,
                    timeout=15.0,
                    headers=_BROWSER_HEADERS,
                    follow_redirects=True,
                ) as client:
                    for page_no in range(1, pages_needed + 1):
                        rows = await _fetch_history_page(client, game_no, game_id, page_no, page_size)
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
                    _CACHE[cache_key] = (time.monotonic(), list(collected))
                    return collected
            except Exception as e:
                last_err = e
                logger.warning("digital history via %s failed [%s/%s]: %s", label, game_id, game_no, e)
                continue

    if last_err:
        logger.warning("digital history exhausted [%s]: %s", game_id, last_err)
    _CACHE[cache_key] = (time.monotonic(), list(collected))
    return collected


async def get_draw_history(game_id: str | None = None, limit: int = 10) -> dict[str, Any]:
    games = [game_id] if game_id in GAME_SPECS else list(GAME_SPECS.keys())
    limit = max(1, min(int(limit or 10), 50))
    results = await asyncio.gather(*[_fetch_history(g, limit) for g in games])
    history = {g: rows for g, rows in zip(games, results)}
    reachable = any(bool(v) for v in history.values())
    return {
        "reachable": reachable,
        "history": history,
        "message": None if reachable else "暂时无法获取官方开奖数据，仍可使用选号与玩法说明。",
    }


async def get_prize_pools(history_limit: int = 30) -> dict[str, Any]:
    """同步各玩法最新奖池，并附带近期每期奖池明细。"""
    history_limit = max(5, min(int(history_limit or 30), 50))
    games = list(GAME_SPECS.keys())
    rows_list = await asyncio.gather(*[_fetch_history(g, history_limit) for g in games])

    pools: dict[str, Any] = {}
    for game_id, rows in zip(games, rows_list):
        spec = GAME_SPECS[game_id]
        latest = rows[0] if rows else None
        history = [
            {
                "issue": r["issue"],
                "draw_time": r.get("draw_time"),
                "result": r.get("result"),
                "pool_balance": r.get("pool_balance"),
                "pool_balance_text": r.get("pool_balance_text"),
                "sale_amount": r.get("sale_amount"),
                "sale_amount_text": r.get("sale_amount_text"),
                "prize_levels": r.get("prize_levels") or [],
            }
            for r in rows
        ]
        pools[game_id] = {
            "game": game_id,
            "name": spec["name"],
            "has_floating_pool": game_id in ("pl5", "qxc", "ssq", "dlt"),
            "pool_note": (
                "固定奖玩法，官方奖池字段通常为 0 或空，以下为接口同步值。"
                if game_id == "pl3"
                else (
                    "开奖后奖池余额（元），来自福利彩票官方开奖公告。"
                    if game_id == "ssq"
                    else "开奖后奖池余额（元），来自体彩官方开奖公告。"
                )
            ),
            "latest": None if not latest else {
                "issue": latest["issue"],
                "draw_time": latest.get("draw_time"),
                "result": latest.get("result"),
                "pool_balance": latest.get("pool_balance"),
                "pool_balance_text": latest.get("pool_balance_text"),
                "sale_amount": latest.get("sale_amount"),
                "sale_amount_text": latest.get("sale_amount_text"),
                "prize_levels": latest.get("prize_levels") or [],
            },
            "history": history,
            "reachable": bool(rows),
        }

    reachable = any(p["reachable"] for p in pools.values())
    return {
        "reachable": reachable,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "message": None if reachable else "暂时无法同步官方奖池数据，请稍后刷新。",
        "pools": pools,
    }


def _normalize_scores(raw: list[float]) -> list[float]:
    lo, hi = min(raw), max(raw)
    if hi - lo < 1e-9:
        return [0.5] * len(raw)
    return [(x - lo) / (hi - lo) for x in raw]


def _analyze_draws(draws: list[dict], alphabets: list[int]) -> dict[str, Any]:
    """按各位字母表统计出现率、遗漏、近窗趋势与综合得分。"""
    n_pos = len(alphabets)
    sample = len(draws) or 1
    recent_n = min(20, sample)
    recent = draws[:recent_n]

    freq = [[0] * alphabets[p] for p in range(n_pos)]
    recent_freq = [[0] * alphabets[p] for p in range(n_pos)]
    last_seen = [[None] * alphabets[p] for p in range(n_pos)]
    overall_count: dict[int, int] = {}
    overall_last: dict[int, int | None] = {}

    for age, row in enumerate(draws):
        digits = row.get("digits") or []
        if len(digits) < n_pos:
            continue
        for pos in range(n_pos):
            d = int(digits[pos])
            if d < 0 or d >= alphabets[pos]:
                continue
            freq[pos][d] += 1
            overall_count[d] = overall_count.get(d, 0) + 1
            if last_seen[pos][d] is None:
                last_seen[pos][d] = age
            if d not in overall_last:
                overall_last[d] = age

    for age, row in enumerate(recent):
        digits = row.get("digits") or []
        if len(digits) < n_pos:
            continue
        for pos in range(n_pos):
            d = int(digits[pos])
            if 0 <= d < alphabets[pos]:
                recent_freq[pos][d] += 1

    position_stats: list[list[dict]] = []
    position_scores: list[list[float]] = []

    for pos in range(n_pos):
        size = alphabets[pos]
        counts = freq[pos]
        rates = [c / sample for c in counts]
        gaps = [last_seen[pos][d] if last_seen[pos][d] is not None else sample for d in range(size)]
        recent_rates = [c / max(1, recent_n) for c in recent_freq[pos]]
        trend = [recent_rates[d] - rates[d] for d in range(size)]

        hot_n = _normalize_scores(rates)
        cold_n = _normalize_scores([float(g) for g in gaps])
        trend_n = _normalize_scores(trend)
        scores = [
            _HOT_WEIGHT * hot_n[d] + _COLD_WEIGHT * cold_n[d] + _TREND_WEIGHT * trend_n[d]
            for d in range(size)
        ]
        position_scores.append(scores)

        ranked_rates = sorted(rates, reverse=True)
        ranked_gaps = sorted(gaps, reverse=True)
        hot_cut = ranked_rates[min(2, size - 1)]
        cold_cut = ranked_gaps[min(2, size - 1)]
        rows = []
        for d in range(size):
            rows.append({
                "digit": d,
                "count": counts[d],
                "rate": round(rates[d], 4),
                "recent_rate": round(recent_rates[d], 4),
                "miss": gaps[d],
                "score": round(scores[d], 4),
                "tag": "hot" if rates[d] >= hot_cut else ("cold" if gaps[d] >= cold_cut else "normal"),
            })
        rows.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))
        position_stats.append(rows)

    # 整体热号：以前区（不含后区特大字母表差异过大时）为主，全部位相加
    front_size = max(alphabets)
    overall_rows = []
    for d in range(min(10, front_size)):
        count = overall_count.get(d, 0)
        rate = count / (sample * n_pos)
        miss = overall_last.get(d)
        if miss is None:
            miss = sample
        overall_rows.append({
            "digit": d,
            "count": count,
            "rate": round(rate, 4),
            "miss": miss,
            "score": 0.0,
        })
    if overall_rows:
        oh = _normalize_scores([r["rate"] for r in overall_rows])
        oc = _normalize_scores([float(r["miss"]) for r in overall_rows])
        for i, r in enumerate(overall_rows):
            r["score"] = round(_HOT_WEIGHT * oh[i] + _COLD_WEIGHT * oc[i], 4)
        overall_rows.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    return {
        "sample_size": sample,
        "alphabets": alphabets,
        "position_stats": position_stats,
        "position_scores": position_scores,
        "overall": overall_rows,
        "hot_digits": [r["digit"] for r in overall_rows[:5]],
        "cold_digits": sorted(
            [r["digit"] for r in overall_rows],
            key=lambda d: (-next(x["miss"] for x in overall_rows if x["digit"] == d), d),
        )[:5],
    }


def _pick_direct_numbers(position_scores: list[list[float]], alphabets: list[int], count: int = 5) -> list[list[int]]:
    n_pos = len(position_scores)
    ranked = [
        sorted(range(alphabets[p]), key=lambda d: (-position_scores[p][d], d))
        for p in range(n_pos)
    ]
    picks: list[list[int]] = []
    used: set[tuple[int, ...]] = set()

    primary = [ranked[p][0] for p in range(n_pos)]
    picks.append(primary)
    used.add(tuple(primary))

    for rank_i in range(1, 4):
        for pos in range(n_pos):
            nums = list(primary)
            nums[pos] = ranked[pos][min(rank_i, alphabets[pos] - 1)]
            key = tuple(nums)
            if key in used:
                continue
            used.add(key)
            picks.append(nums)
            if len(picks) >= count:
                return picks

    secondary = [ranked[p][min(1, alphabets[p] - 1)] for p in range(n_pos)]
    if tuple(secondary) not in used:
        picks.append(secondary)
    return picks[:count]


def _cold_pick(analysis: dict[str, Any]) -> list[int]:
    cold = []
    for pos_stats in analysis["position_stats"]:
        by_miss = sorted(pos_stats, key=lambda x: (-x["miss"], -x["score"], x["digit"]))
        cold.append(by_miss[0]["digit"])
    return cold


def _build_recommendations(game_id: str, draws: list[dict], analysis: dict[str, Any]) -> list[dict]:
    """每种玩法固定输出 5 注直选参考号（去冗余）。"""
    alphabets = analysis["alphabets"]
    n_pos = len(alphabets)
    scores = analysis["position_scores"]
    directs = _pick_direct_numbers(scores, alphabets, count=5)

    # 第 5 注尽量用冷号回补，增加多样性
    cold_pick = _cold_pick(analysis)
    used = {tuple(x) for x in directs}
    if len(directs) >= 5 and tuple(cold_pick) not in used:
        directs[4] = cold_pick
    elif len(directs) < 5 and tuple(cold_pick) not in used:
        directs.append(cold_pick)

    recs: list[dict] = []
    for i, nums in enumerate(directs[:5]):
        conf = sum(scores[p][nums[p]] for p in range(n_pos)) / n_pos
        is_cold = nums == cold_pick
        recs.append({
            "id": f"pick-{i + 1}",
            "mode": "direct",
            "source": "frequency",
            "label": f"推荐 {i + 1}",
            "digits": nums,
            "display": " ".join(str(x) for x in nums),
            "confidence": round(conf, 4),
            "reason": (
                "冷号回补：各位遗漏偏大，作均衡参考"
                if is_cold
                else "各位历史出现率 + 遗漏 + 近窗趋势综合得分"
            ),
            "bets": 1,
        })
    return recs


def _merge_recommendations(
    freq_recs: list[dict],
    ai_picks: list[dict],
    limit: int = 5,
) -> list[dict]:
    """AI 精选优先去重合并，总数严格限制为 limit。"""
    merged: list[dict] = []
    seen: set[tuple[int, ...]] = set()
    for rec in list(ai_picks) + list(freq_recs):
        digits = rec.get("digits") or []
        key = tuple(digits)
        if not digits or key in seen:
            continue
        seen.add(key)
        merged.append(rec)
        if len(merged) >= limit:
            break
    for i, rec in enumerate(merged):
        rec["id"] = f"pick-{i + 1}"
        if rec.get("source") == "ai":
            model_label = rec.get("model_label") or "AI"
            rec["label"] = f"推荐 {i + 1} · {model_label}"
        else:
            rec["label"] = f"推荐 {i + 1}"
    return merged


def _validate_ai_digits(digits: list, alphabets: list[int]) -> list[int] | None:
    if not isinstance(digits, list) or len(digits) != len(alphabets):
        return None
    out = []
    for i, raw in enumerate(digits):
        try:
            d = int(raw)
        except (TypeError, ValueError):
            return None
        if d < 0 or d >= alphabets[i]:
            return None
        out.append(d)
    return out


async def _ai_refine_picks(
    game_id: str,
    analysis: dict[str, Any],
    draws: list[dict],
    base_recs: list[dict],
) -> list[dict]:
    """DeepSeek / 千问 / GLM 并行精选，按共识融合，最多返回 3 注。"""
    from service.digital_ai import (
        configured_digital_models,
        fuse_ai_picks,
        gather_digital_llm_json,
    )

    if not configured_digital_models():
        return []

    spec = GAME_SPECS[game_id]
    alphabets = spec["alphabets"]
    top_by_pos = []
    for pos, rows in enumerate(analysis["position_stats"]):
        top_by_pos.append({
            "pos": pos,
            "top": [{"digit": r["digit"], "rate": r["rate"], "miss": r["miss"], "score": r["score"]} for r in rows[:5]],
        })
    recent = [{"issue": d["issue"], "result": d["result"]} for d in draws[:12]]
    seed = [{"display": r["display"], "confidence": r["confidence"]} for r in base_recs[:5] if r["mode"] == "direct"]

    prompt = (
        f"你是体彩{spec['name']}选号分析助手。根据历史频率与遗漏给出购彩参考号，"
        "不要声称必中。严格输出 JSON。\n"
        f"玩法: {game_id}, 各位取值上限(含): {[a - 1 for a in alphabets]}\n"
        f"样本期数: {analysis['sample_size']}\n"
        f"各位Top统计: {json.dumps(top_by_pos, ensure_ascii=False)}\n"
        f"频率引擎候选: {json.dumps(seed, ensure_ascii=False)}\n"
        f"近12期开奖: {json.dumps(recent, ensure_ascii=False)}\n"
        "返回格式:\n"
        '{"picks":[{"digits":[...],"reason":"一句话","confidence":0.0到1.0}],'
        '"summary":"一句话策略说明"}\n'
        "要求: picks 恰好 2 注；digits 长度与位数一致；七星彩末位可为0-14；尽量与候选不完全重复。"
    )

    model_results = await gather_digital_llm_json(prompt)

    def extract_items(parsed: dict) -> list[dict]:
        picks = parsed.get("picks")
        return picks if isinstance(picks, list) else []

    def build_rec(digits, conf, reason, _models):
        return {
            "mode": "direct",
            "label": "AI 精选",
            "digits": digits,
            "display": " ".join(str(x) for x in digits),
            "confidence": conf,
            "reason": reason,
            "bets": 1,
        }

    return fuse_ai_picks(
        model_results,
        extract_items=extract_items,
        validate_item=lambda item: _validate_ai_digits(item.get("digits") or [], alphabets),
        build_rec=build_rec,
        limit=3,
    )

async def get_recommendations(
    game_id: str,
    window: int = 100,
    use_ai: bool = True,
) -> dict[str, Any]:
    from service.digital_ai import rec_cache_get, rec_cache_set

    if game_id not in GAME_SPECS:
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
            "ai_enabled": False,
        }

    if game_id == "ssq":
        return await get_ssq_recommendations(window=window, use_ai=use_ai)
    if game_id == "dlt":
        return await get_dlt_recommendations(window=window, use_ai=use_ai)

    window = max(20, min(int(window or 100), 200))
    cache_key = f"rec:{game_id}:{window}:{int(bool(use_ai))}"
    cached = rec_cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return cached

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
            "ai_enabled": False,
        }

    alphabets = GAME_SPECS[game_id]["alphabets"]
    analysis = _analyze_draws(draws, alphabets)
    freq_recs = _build_recommendations(game_id, draws, analysis)

    ai_picks: list[dict] = []
    from service.digital_ai import configured_digital_models, model_display_name

    configured = configured_digital_models()
    ai_enabled = bool(configured) and use_ai
    if ai_enabled:
        ai_picks = await _ai_refine_picks(game_id, analysis, draws, freq_recs)

    recs = _merge_recommendations(freq_recs, ai_picks, limit=5)
    model_names = sorted({
        model_display_name(m)
        for r in ai_picks
        for m in (r.get("models") or [])
    })

    payload = {
        "reachable": True,
        "message": None,
        "game": game_id,
        "window": window,
        "sample_size": analysis["sample_size"],
        "alphabets": alphabets,
        "method": {
            "hot_weight": _HOT_WEIGHT,
            "cold_weight": _COLD_WEIGHT,
            "trend_weight": _TREND_WEIGHT,
            "ai_enabled": bool(ai_picks),
            "ai_models": model_names,
            "pick_limit": 5,
            "desc": (
                "每种玩法固定推荐 5 注；基于历史出现概率、遗漏与近窗趋势"
                + (
                    f"，并由 {'+'.join(model_names)} 多模型精选前几注。"
                    if ai_picks and model_names
                    else ("，并由 AI 精选前几注。" if ai_picks else "。")
                )
            ),
        },
        "disclaimer": "历史频率与 AI 建议均不代表下期必然开出，请勿作为必中依据。",
        "recommendations": recs,
        "position_stats": analysis["position_stats"],
        "overall": analysis["overall"],
        "hot_digits": analysis["hot_digits"],
        "cold_digits": analysis["cold_digits"],
        "history_preview": draws[:15],
        "latest": draws[0] if draws else None,
        "ai_enabled": bool(ai_picks),
        "ai_models": model_names,
        "cached": False,
    }
    rec_cache_set(cache_key, payload)
    return payload
