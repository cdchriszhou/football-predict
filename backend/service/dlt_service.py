"""体彩超级大乐透 — 开奖拉取、频率推荐与多模型 AI 精选。"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from utils.http_client import sporttery_proxy_attempts
from utils.logger import logger

DLT_GAME = {
    "id": "dlt",
    "name": "大乐透",
    "name_en": "Super Lotto",
    "kind": "dlt",
    "front_count": 5,
    "front_max": 35,
    "back_count": 2,
    "back_max": 12,
    "price_per_bet": 2,
    "draw_cycle": "mon_wed_sat",
    "note": "前区从 01–35 选 5 个（不重复），后区从 01–12 选 2 个（不重复）；每周一、三、六开奖。",
    "play_types": [
        {
            "id": "single",
            "name": "单式投注",
            "prize": None,
            "prize_label": "一等奖浮动（最高1000万）",
            "desc": "前区 5 个 + 后区 2 个全部命中为一等奖；另有二至九等奖。",
        },
    ],
}

_HISTORY_URL = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
_GAME_NOS = ("85",)
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
_TREND_WEIGHT = 0.10


def clear_dlt_history_cache() -> None:
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


def _normalize_scores(raw: list[float]) -> list[float]:
    lo, hi = min(raw), max(raw)
    if hi - lo < 1e-9:
        return [0.5] * len(raw)
    return [(x - lo) / (hi - lo) for x in raw]


def _fmt_ball(n: int) -> str:
    return f"{int(n):02d}"


def _normalize_dlt_row(raw: dict) -> dict[str, Any] | None:
    issue = raw.get("lotteryDrawNum") or raw.get("issue") or raw.get("code")
    result = (
        raw.get("lotteryDrawResult")
        or raw.get("lotteryUnsortDrawresult")
        or raw.get("result")
    )
    draw_time = raw.get("lotteryDrawTime") or raw.get("drawTime") or raw.get("date")
    if not issue or result is None:
        return None

    text = str(result).replace("+", " ").replace(",", " ").replace("|", " ")
    nums: list[int] = []
    for tok in text.split():
        try:
            n = int(tok)
        except ValueError:
            continue
        nums.append(n)

    if len(nums) < 7:
        return None

    front = sorted({n for n in nums[:5] if 1 <= n <= 35})
    back = sorted({n for n in nums[5:7] if 1 <= n <= 12})
    if len(front) != 5 or len(back) != 2:
        return None

    pool = _parse_money(
        raw.get("poolBalanceAfterdraw")
        or raw.get("poolBalance")
        or raw.get("poolmoney")
    )
    sale = _parse_money(raw.get("totalSaleAmount") or raw.get("sales") or raw.get("saleAmount"))

    return {
        "issue": str(issue),
        "result": " ".join(_fmt_ball(x) for x in front) + " + " + " ".join(_fmt_ball(x) for x in back),
        "digits": front + back,
        "front": front,
        "back": back,
        "draw_time": draw_time,
        "sale_amount": sale,
        "sale_amount_text": _format_money(sale),
        "pool_balance": pool,
        "pool_balance_text": _format_money(pool),
        "prize_levels": [],
        "has_floating_pool": True,
        "kind": "dlt",
    }


async def fetch_dlt_history(limit: int = 100, *, force_refresh: bool = False) -> list[dict]:
    limit = max(1, min(int(limit or 100), 100))
    cache_key = f"dlt:{limit}"
    now = time.monotonic()
    if force_refresh:
        _CACHE.pop(cache_key, None)
    else:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SEC:
            return list(cached[1])

    page_size = min(50, limit)
    pages_needed = (limit + page_size - 1) // page_size
    collected: list[dict] = []

    for game_no in _GAME_NOS:
        for label, proxy in sporttery_proxy_attempts():
            collected = []
            seen: set[str] = set()
            try:
                async with httpx.AsyncClient(
                    proxy=proxy,
                    timeout=15.0,
                    headers=_BROWSER_HEADERS,
                    follow_redirects=True,
                ) as client:
                    for page_no in range(1, pages_needed + 1):
                        params = {
                            "gameNo": game_no,
                            "provinceId": "0",
                            "pageSize": str(page_size),
                            "isVerify": "1",
                            "pageNo": str(page_no),
                        }
                        resp = await client.get(_HISTORY_URL, params=params)
                        if resp.status_code != 200:
                            break
                        payload = resp.json()
                        rows = ((payload.get("value") or {}).get("list") or []) if isinstance(payload, dict) else []
                        if not rows:
                            break
                        for raw in rows:
                            if not isinstance(raw, dict):
                                continue
                            item = _normalize_dlt_row(raw)
                            if not item or item["issue"] in seen:
                                continue
                            seen.add(item["issue"])
                            collected.append(item)
                            if len(collected) >= limit:
                                break
                        if len(collected) >= limit or len(rows) < page_size:
                            break
                if collected:
                    _CACHE[cache_key] = (time.monotonic(), list(collected))
                    return collected
            except Exception as e:
                logger.warning("dlt history via %s failed [%s]: %s", label, game_no, e)
                continue

    _CACHE[cache_key] = (time.monotonic(), list(collected))
    return collected


def _score_pool(counts: list[int], gaps: list[int], recent_counts: list[int], sample: int, recent_n: int) -> list[float]:
    size = len(counts)
    rates = [c / sample for c in counts]
    recent_rates = [c / max(1, recent_n) for c in recent_counts]
    trend = [recent_rates[i] - rates[i] for i in range(size)]
    hot_n = _normalize_scores(rates)
    cold_n = _normalize_scores([float(g) for g in gaps])
    trend_n = _normalize_scores(trend)
    return [
        _HOT_WEIGHT * hot_n[i] + _COLD_WEIGHT * cold_n[i] + _TREND_WEIGHT * trend_n[i]
        for i in range(size)
    ]


def analyze_dlt(draws: list[dict]) -> dict[str, Any]:
    sample = len(draws) or 1
    recent_n = min(20, sample)
    recent = draws[:recent_n]

    front_count = [0] * 36
    back_count = [0] * 13
    front_last = [None] * 36
    back_last = [None] * 13
    front_recent = [0] * 36
    back_recent = [0] * 13

    for age, row in enumerate(draws):
        for n in row.get("front") or []:
            if 1 <= n <= 35:
                front_count[n] += 1
                if front_last[n] is None:
                    front_last[n] = age
        for n in row.get("back") or []:
            if 1 <= n <= 12:
                back_count[n] += 1
                if back_last[n] is None:
                    back_last[n] = age

    for row in recent:
        for n in row.get("front") or []:
            if 1 <= n <= 35:
                front_recent[n] += 1
        for n in row.get("back") or []:
            if 1 <= n <= 12:
                back_recent[n] += 1

    front_gaps = [front_last[i] if front_last[i] is not None else sample for i in range(36)]
    back_gaps = [back_last[i] if back_last[i] is not None else sample for i in range(13)]
    front_scores = _score_pool(front_count[1:], front_gaps[1:], front_recent[1:], sample, recent_n)
    back_scores = _score_pool(back_count[1:], back_gaps[1:], back_recent[1:], sample, recent_n)
    front_score_map = {i + 1: front_scores[i] for i in range(35)}
    back_score_map = {i + 1: back_scores[i] for i in range(12)}

    front_rates = [front_count[i] / sample for i in range(1, 36)]
    front_hot_cut = sorted(front_rates, reverse=True)[4]
    front_cold_cut = sorted(front_gaps[1:], reverse=True)[4]
    front_stats = []
    for n in range(1, 36):
        rate = front_count[n] / sample
        front_stats.append({
            "digit": n,
            "count": front_count[n],
            "rate": round(rate, 4),
            "miss": front_gaps[n],
            "score": round(front_score_map[n], 4),
            "tag": "hot" if rate >= front_hot_cut else (
                "cold" if front_gaps[n] >= front_cold_cut else "normal"
            ),
        })
    front_stats.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    back_rates = [back_count[i] / sample for i in range(1, 13)]
    back_hot_cut = sorted(back_rates, reverse=True)[min(2, len(back_rates) - 1)]
    back_cold_cut = sorted(back_gaps[1:], reverse=True)[min(2, len(back_gaps) - 2)]
    back_stats = []
    for n in range(1, 13):
        rate = back_count[n] / sample
        back_stats.append({
            "digit": n,
            "count": back_count[n],
            "rate": round(rate, 4),
            "miss": back_gaps[n],
            "score": round(back_score_map[n], 4),
            "tag": "hot" if rate >= back_hot_cut else (
                "cold" if back_gaps[n] >= back_cold_cut else "normal"
            ),
        })
    back_stats.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    return {
        "sample_size": sample,
        "kind": "dlt",
        "front_stats": front_stats,
        "back_stats": back_stats,
        "front_score_map": front_score_map,
        "back_score_map": back_score_map,
        "hot_digits": [r["digit"] for r in front_stats[:5]],
        "cold_digits": sorted(range(1, 36), key=lambda d: (-front_gaps[d], d))[:5],
        "hot_back": [r["digit"] for r in back_stats[:2]],
        "cold_back": sorted(range(1, 13), key=lambda d: (-back_gaps[d], d))[:2],
        "position_stats": [front_stats, back_stats],
        "alphabets": [35, 12],
        "overall": front_stats[:10],
    }


def _pick_dlt_sets(analysis: dict[str, Any], count: int = 5) -> list[tuple[list[int], list[int]]]:
    front_ranked = [r["digit"] for r in analysis["front_stats"]]
    back_ranked = [b["digit"] for b in analysis["back_stats"]]
    cold_front = analysis["cold_digits"]
    cold_back = analysis["cold_back"]

    picks: list[tuple[list[int], list[int]]] = []
    used: set[tuple[int, ...]] = set()

    def add(fronts: list[int], backs: list[int]) -> None:
        fronts = sorted(set(fronts))
        backs = sorted(set(backs))
        if len(fronts) != 5 or len(backs) != 2:
            return
        if any(n < 1 or n > 35 for n in fronts):
            return
        if any(n < 1 or n > 12 for n in backs):
            return
        key = tuple(fronts + backs)
        if key in used:
            return
        used.add(key)
        picks.append((fronts, backs))

    add(front_ranked[:5], back_ranked[:2])
    add(front_ranked[1:6], back_ranked[1:3] if len(back_ranked) >= 3 else back_ranked[:2])
    mix = sorted(set(front_ranked[:3] + cold_front[:2]))[:5]
    if len(mix) < 5:
        for n in front_ranked:
            if n not in mix:
                mix.append(n)
            if len(mix) >= 5:
                break
    add(sorted(mix[:5]), back_ranked[:2])
    add(sorted(cold_front[:5]), cold_back[:2] if len(cold_back) >= 2 else back_ranked[-2:])
    odd = [n for n in front_ranked if n % 2 == 1]
    even = [n for n in front_ranked if n % 2 == 0]
    bal = sorted((odd[:3] + even[:2])[:5])
    add(bal, [back_ranked[0], back_ranked[min(2, len(back_ranked) - 1)]])

    offset = 2
    while len(picks) < count and offset < 25:
        add(front_ranked[offset:offset + 5], [
            back_ranked[offset % len(back_ranked)],
            back_ranked[(offset + 1) % len(back_ranked)],
        ])
        offset += 1

    return picks[:count]


def build_dlt_recommendations(analysis: dict[str, Any]) -> list[dict]:
    front_map = analysis["front_score_map"]
    back_map = analysis["back_score_map"]
    picks = _pick_dlt_sets(analysis, count=5)
    recs = []
    for i, (fronts, backs) in enumerate(picks):
        conf = (
            sum(front_map[n] for n in fronts) / 5
            + sum(back_map[n] for n in backs) / 2
        ) / 2
        reason = "前区/后区历史出现率 + 遗漏 + 近窗趋势综合"
        if i == 3:
            reason = "冷号回补：遗漏偏大的前后区号码作均衡参考"
        recs.append({
            "id": f"pick-{i + 1}",
            "mode": "dlt",
            "source": "frequency",
            "label": f"推荐 {i + 1}",
            "digits": fronts + backs,
            "front": fronts,
            "back": backs,
            "display": (
                " ".join(_fmt_ball(x) for x in fronts)
                + " + "
                + " ".join(_fmt_ball(x) for x in backs)
            ),
            "confidence": round(conf, 4),
            "reason": reason,
            "bets": 1,
        })
    return recs


def _validate_dlt_ai(item: dict) -> tuple[list[int], list[int]] | None:
    fronts = item.get("front") or item.get("red")
    backs = item.get("back") or item.get("blue")
    digits = item.get("digits")
    if isinstance(digits, list) and len(digits) >= 7 and fronts is None:
        fronts = digits[:5]
        backs = digits[5:7]
    if not isinstance(fronts, list) or not isinstance(backs, list):
        return None
    try:
        fronts_i = sorted({int(x) for x in fronts})
        backs_i = sorted({int(x) for x in backs})
    except (TypeError, ValueError):
        return None
    if len(fronts_i) != 5 or len(backs_i) != 2:
        return None
    if any(n < 1 or n > 35 for n in fronts_i):
        return None
    if any(n < 1 or n > 12 for n in backs_i):
        return None
    return fronts_i, backs_i


async def ai_refine_dlt(analysis: dict[str, Any], draws: list[dict], base_recs: list[dict]) -> list[dict]:
    from service.digital_ai import (
        configured_digital_models,
        fuse_ai_picks,
        gather_digital_llm_json,
    )

    if not configured_digital_models():
        return []

    recent = [{"issue": d["issue"], "result": d["result"]} for d in draws[:12]]
    seed = [{"display": r["display"], "confidence": r["confidence"]} for r in base_recs[:5]]
    prompt = (
        "你是体育彩票超级大乐透选号分析助手。根据历史频率与遗漏给出购彩参考号，不要声称必中。严格输出 JSON。\n"
        "规则: 前区 5 个不重复整数 1-35，后区 2 个不重复整数 1-12。\n"
        f"样本期数: {analysis['sample_size']}\n"
        f"热前区: {analysis['hot_digits']}, 冷前区: {analysis['cold_digits']}\n"
        f"热后区: {analysis['hot_back']}, 冷后区: {analysis['cold_back']}\n"
        f"频率候选: {json.dumps(seed, ensure_ascii=False)}\n"
        f"近12期: {json.dumps(recent, ensure_ascii=False)}\n"
        '返回: {"picks":[{"front":[1,2,3,4,5],"back":[6,7],"reason":"一句话","confidence":0.7}],"summary":"..."}\n'
        "要求: picks 恰好 2 注；尽量与候选不完全重复。"
    )

    model_results = await gather_digital_llm_json(prompt)

    def extract_items(parsed: dict) -> list[dict]:
        picks = parsed.get("picks")
        return picks if isinstance(picks, list) else []

    def build_rec(validated, conf, reason, _models):
        fronts, backs = validated
        return {
            "mode": "dlt",
            "label": "AI 精选",
            "digits": fronts + backs,
            "front": fronts,
            "back": backs,
            "display": (
                " ".join(_fmt_ball(x) for x in fronts)
                + " + "
                + " ".join(_fmt_ball(x) for x in backs)
            ),
            "confidence": conf,
            "reason": reason,
            "bets": 1,
        }

    return fuse_ai_picks(
        model_results,
        extract_items=extract_items,
        validate_item=_validate_dlt_ai,
        build_rec=build_rec,
        limit=3,
    )


async def get_dlt_recommendations(
    window: int = 100,
    use_ai: bool = True,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    from service.digital_ai import (
        configured_digital_models,
        model_display_name,
        rec_cache_get,
        rec_cache_invalidate,
        rec_cache_set,
    )

    window = max(20, min(int(window or 100), 100))
    cache_key = f"rec:dlt:{window}:{int(bool(use_ai))}"
    if force_refresh:
        clear_dlt_history_cache()
        rec_cache_invalidate("dlt")
    else:
        cached = rec_cache_get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

    draws = await fetch_dlt_history(window, force_refresh=force_refresh)
    if not draws:
        return {
            "reachable": False,
            "message": "暂时无法获取大乐透官方开奖数据，无法生成频率推荐。请稍后刷新。",
            "game": "dlt",
            "window": window,
            "sample_size": 0,
            "recommendations": [],
            "position_stats": [],
            "overall": [],
            "hot_digits": [],
            "cold_digits": [],
            "ai_enabled": False,
            "ai_models": [],
        }

    analysis = analyze_dlt(draws)
    freq_recs = build_dlt_recommendations(analysis)
    ai_picks: list[dict] = []
    configured = configured_digital_models()
    if use_ai and configured:
        ai_picks = await ai_refine_dlt(analysis, draws, freq_recs)

    merged: list[dict] = []
    seen: set[tuple] = set()
    for rec in list(ai_picks) + list(freq_recs):
        key = tuple(rec.get("digits") or [])
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(rec)
        if len(merged) >= 5:
            break
    for i, rec in enumerate(merged):
        rec["id"] = f"pick-{i + 1}"
        if rec.get("source") == "ai":
            model_label = rec.get("model_label") or "AI"
            rec["label"] = f"推荐 {i + 1} · {model_label}"
        else:
            rec["label"] = f"推荐 {i + 1}"

    model_names = sorted({
        model_display_name(m)
        for r in ai_picks
        for m in (r.get("models") or [])
    })

    payload = {
        "reachable": True,
        "message": None,
        "game": "dlt",
        "window": window,
        "sample_size": analysis["sample_size"],
        "kind": "dlt",
        "alphabets": [35, 12],
        "method": {
            "hot_weight": _HOT_WEIGHT,
            "cold_weight": _COLD_WEIGHT,
            "trend_weight": _TREND_WEIGHT,
            "ai_enabled": bool(ai_picks),
            "ai_models": model_names,
            "pick_limit": 5,
            "desc": (
                "大乐透固定推荐 5 注；前/后区字母表内全部号码参与评分（含样本期内从未出现的冷号），"
                "分别统计历史出现概率、遗漏与近窗趋势"
                + (
                    f"，并由 {'+'.join(model_names)} 多模型精选前几注。"
                    if ai_picks and model_names
                    else ("，并由 AI 精选前几注。" if ai_picks else "。")
                )
            ),
        },
        "disclaimer": "历史频率与 AI 建议均不代表下期必然开出，请勿作为必中依据。大乐透为体育彩票玩法。",
        "recommendations": merged,
        "position_stats": analysis["position_stats"],
        "overall": analysis["overall"],
        "hot_digits": analysis["hot_digits"],
        "cold_digits": analysis["cold_digits"],
        "hot_back": analysis["hot_back"],
        "cold_back": analysis["cold_back"],
        "history_preview": draws[:15],
        "latest": draws[0] if draws else None,
        "ai_enabled": bool(ai_picks),
        "ai_models": model_names,
        "cached": False,
    }
    rec_cache_set(cache_key, payload)
    return payload
