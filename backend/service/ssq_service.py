"""福利彩票双色球 — 开奖拉取、频率推荐与可选 AI 精选。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx

from utils.http_client import get_crawler_proxy
from utils.logger import logger

SSQ_GAME = {
    "id": "ssq",
    "name": "双色球",
    "name_en": "Double Color Ball",
    "kind": "ssq",
    "red_count": 6,
    "red_max": 33,
    "blue_max": 16,
    "price_per_bet": 2,
    "draw_cycle": "tue_thu_sun",
    "note": "红球从 01–33 中选 6 个（不重复），蓝球从 01–16 中选 1 个；每周二、四、日开奖。",
    "play_types": [
        {
            "id": "single",
            "name": "单式投注",
            "prize": None,
            "prize_label": "一等奖浮动（最高1000万）",
            "desc": "6 个红球 + 1 个蓝球全部命中为一等奖；另有二至六等奖。",
        },
    ],
}

_SSQ_URLS = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
    "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice",
)
_SSQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.cwl.gov.cn/kjxx/ssq/",
    "Accept": "application/json, text/plain, */*",
}

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 600

_HOT_WEIGHT = 0.65
_COLD_WEIGHT = 0.25
_TREND_WEIGHT = 0.10


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


def _normalize_ssq_row(raw: dict) -> dict[str, Any] | None:
    issue = raw.get("code") or raw.get("issue") or raw.get("lotteryDrawNum")
    red_raw = raw.get("red") or raw.get("redBall") or ""
    blue_raw = raw.get("blue") or raw.get("blueBall") or ""
    draw_time = raw.get("date") or raw.get("lotteryDrawTime") or raw.get("drawTime")
    if not issue:
        return None

    reds: list[int] = []
    for tok in re.split(r"[,，\s]+", str(red_raw).strip()):
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            continue
        if 1 <= n <= 33 and n not in reds:
            reds.append(n)
    if len(reds) != 6:
        return None
    reds = sorted(reds)

    try:
        blue = int(str(blue_raw).strip())
    except ValueError:
        return None
    if not (1 <= blue <= 16):
        return None

    pool = _parse_money(raw.get("poolmoney") or raw.get("poolMoney") or raw.get("pool_balance"))
    sale = _parse_money(raw.get("sales") or raw.get("saleAmount") or raw.get("totalSaleAmount"))

    return {
        "issue": str(issue),
        "result": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
        "digits": reds + [blue],
        "red": reds,
        "blue": blue,
        "draw_time": draw_time,
        "sale_amount": sale,
        "sale_amount_text": _format_money(sale),
        "pool_balance": pool,
        "pool_balance_text": _format_money(pool),
        "prize_levels": [],
        "has_floating_pool": True,
        "kind": "ssq",
    }


async def fetch_ssq_history(limit: int = 100) -> list[dict]:
    limit = max(1, min(int(limit or 100), 100))
    cache_key = f"ssq:{limit}"
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return list(cached[1])

    params = {
        "name": "ssq",
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
    for url in _SSQ_URLS:
        for proxy in proxies:
            try:
                async with httpx.AsyncClient(
                    proxy=proxy,
                    timeout=15.0,
                    headers=_SSQ_HEADERS,
                    follow_redirects=True,
                ) as client:
                    # issueCount 接口一次最多约 30；多页拉取
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
                            logger.warning("ssq history HTTP %s via %s page %s", resp.status_code, url, page)
                            break
                        payload = resp.json()
                        result = payload.get("result") if isinstance(payload, dict) else None
                        if not isinstance(result, list):
                            # 有些接口把列表放在 data
                            result = payload.get("data") if isinstance(payload, dict) else None
                        if not isinstance(result, list) or not result:
                            break
                        for raw in result:
                            if not isinstance(raw, dict):
                                continue
                            item = _normalize_ssq_row(raw)
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
                logger.warning("ssq history failed [%s]: %s", url, e)
                continue
        if collected:
            break

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


def analyze_ssq(draws: list[dict]) -> dict[str, Any]:
    sample = len(draws) or 1
    recent_n = min(20, sample)
    recent = draws[:recent_n]

    red_count = [0] * 34  # index 1..33
    blue_count = [0] * 17  # index 1..16
    red_last = [None] * 34
    blue_last = [None] * 17
    red_recent = [0] * 34
    blue_recent = [0] * 17

    for age, row in enumerate(draws):
        for n in row.get("red") or []:
            if 1 <= n <= 33:
                red_count[n] += 1
                if red_last[n] is None:
                    red_last[n] = age
        b = row.get("blue")
        if isinstance(b, int) and 1 <= b <= 16:
            blue_count[b] += 1
            if blue_last[b] is None:
                blue_last[b] = age

    for row in recent:
        for n in row.get("red") or []:
            if 1 <= n <= 33:
                red_recent[n] += 1
        b = row.get("blue")
        if isinstance(b, int) and 1 <= b <= 16:
            blue_recent[b] += 1

    red_gaps = [red_last[i] if red_last[i] is not None else sample for i in range(34)]
    blue_gaps = [blue_last[i] if blue_last[i] is not None else sample for i in range(17)]
    red_scores = _score_pool(red_count[1:], red_gaps[1:], red_recent[1:], sample, recent_n)
    blue_scores = _score_pool(blue_count[1:], blue_gaps[1:], blue_recent[1:], sample, recent_n)
    # pad index 0 unused for convenience aligning with ball numbers via +1
    red_score_map = {i + 1: red_scores[i] for i in range(33)}
    blue_score_map = {i + 1: blue_scores[i] for i in range(16)}

    red_stats = []
    for n in range(1, 34):
        rate = red_count[n] / sample
        red_stats.append({
            "digit": n,
            "count": red_count[n],
            "rate": round(rate, 4),
            "miss": red_gaps[n],
            "score": round(red_score_map[n], 4),
            "tag": "hot" if rate >= sorted([red_count[i] / sample for i in range(1, 34)], reverse=True)[5] else (
                "cold" if red_gaps[n] >= sorted(red_gaps[1:], reverse=True)[5] else "normal"
            ),
        })
    red_stats.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    blue_stats = []
    for n in range(1, 17):
        rate = blue_count[n] / sample
        blue_stats.append({
            "digit": n,
            "count": blue_count[n],
            "rate": round(rate, 4),
            "miss": blue_gaps[n],
            "score": round(blue_score_map[n], 4),
            "tag": "hot" if rate >= sorted([blue_count[i] / sample for i in range(1, 17)], reverse=True)[2] else (
                "cold" if blue_gaps[n] >= sorted(blue_gaps[1:], reverse=True)[2] else "normal"
            ),
        })
    blue_stats.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    return {
        "sample_size": sample,
        "kind": "ssq",
        "red_stats": red_stats,
        "blue_stats": blue_stats,
        "red_score_map": red_score_map,
        "blue_score_map": blue_score_map,
        "hot_digits": [r["digit"] for r in red_stats[:6]],
        "cold_digits": sorted(range(1, 34), key=lambda d: (-red_gaps[d], d))[:6],
        "hot_blue": [r["digit"] for r in blue_stats[:3]],
        "cold_blue": sorted(range(1, 17), key=lambda d: (-blue_gaps[d], d))[:3],
        # UI 兼容：把红球统计映射到 position_stats[0]，蓝球到 position_stats[1]
        "position_stats": [red_stats, blue_stats],
        "alphabets": [33, 16],
        "overall": red_stats[:10],
    }


def _pick_ssq_sets(analysis: dict[str, Any], count: int = 5) -> list[tuple[list[int], int]]:
    red_ranked = [r["digit"] for r in analysis["red_stats"]]
    blue_ranked = [b["digit"] for b in analysis["blue_stats"]]
    cold_red = analysis["cold_digits"]
    cold_blue = analysis["cold_blue"]

    picks: list[tuple[list[int], int]] = []
    used: set[tuple[int, ...]] = set()

    def add(reds: list[int], blue: int) -> None:
        reds = sorted(set(reds))
        if len(reds) != 6 or not (1 <= blue <= 16):
            return
        key = tuple(reds + [blue])
        if key in used:
            return
        used.add(key)
        picks.append((reds, blue))

    # 1 主推：热红 + 热蓝
    add(red_ranked[:6], blue_ranked[0])
    # 2 次热红 + 次热蓝
    add(red_ranked[1:7], blue_ranked[min(1, len(blue_ranked) - 1)])
    # 3 热红混一点冷红
    mix = sorted(set(red_ranked[:4] + cold_red[:2]))[:6]
    if len(mix) < 6:
        for n in red_ranked:
            if n not in mix:
                mix.append(n)
            if len(mix) >= 6:
                break
    add(sorted(mix[:6]), blue_ranked[0])
    # 4 冷号回补
    add(sorted(cold_red[:6]), cold_blue[0] if cold_blue else blue_ranked[-1])
    # 5 交错：奇偶均衡倾向
    odd = [n for n in red_ranked if n % 2 == 1]
    even = [n for n in red_ranked if n % 2 == 0]
    bal = sorted((odd[:3] + even[:3])[:6])
    add(bal, blue_ranked[min(2, len(blue_ranked) - 1)])

    # 补足
    offset = 2
    while len(picks) < count and offset < 20:
        add(red_ranked[offset:offset + 6], blue_ranked[offset % len(blue_ranked)])
        offset += 1

    return picks[:count]


def build_ssq_recommendations(analysis: dict[str, Any]) -> list[dict]:
    red_map = analysis["red_score_map"]
    blue_map = analysis["blue_score_map"]
    picks = _pick_ssq_sets(analysis, count=5)
    recs = []
    for i, (reds, blue) in enumerate(picks):
        conf = (sum(red_map[n] for n in reds) / 6 + blue_map[blue]) / 2
        reason = "红球/蓝球历史出现率 + 遗漏 + 近窗趋势综合"
        if i == 3:
            reason = "冷号回补：遗漏偏大的红蓝球作均衡参考"
        recs.append({
            "id": f"pick-{i + 1}",
            "mode": "ssq",
            "source": "frequency",
            "label": f"推荐 {i + 1}",
            "digits": reds + [blue],
            "red": reds,
            "blue": blue,
            "display": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
            "confidence": round(conf, 4),
            "reason": reason,
            "bets": 1,
        })
    return recs


def _validate_ssq_ai(item: dict) -> tuple[list[int], int] | None:
    reds = item.get("red") or item.get("digits")
    blue = item.get("blue")
    if isinstance(reds, list) and len(reds) >= 7 and blue is None:
        blue = reds[6]
        reds = reds[:6]
    if not isinstance(reds, list) or blue is None:
        return None
    try:
        reds_i = sorted({int(x) for x in reds})
        blue_i = int(blue)
    except (TypeError, ValueError):
        return None
    if len(reds_i) != 6:
        return None
    if any(n < 1 or n > 33 for n in reds_i):
        return None
    if blue_i < 1 or blue_i > 16:
        return None
    return reds_i, blue_i


async def ai_refine_ssq(analysis: dict[str, Any], draws: list[dict], base_recs: list[dict]) -> list[dict]:
    """DeepSeek / 千问 / GLM 并行精选双色球，按共识融合。"""
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
        "你是福利彩票双色球选号分析助手。根据历史频率与遗漏给出购彩参考号，不要声称必中。严格输出 JSON。\n"
        "规则: 红球 6 个不重复整数 1-33，蓝球 1 个整数 1-16。\n"
        f"样本期数: {analysis['sample_size']}\n"
        f"热红: {analysis['hot_digits']}, 冷红: {analysis['cold_digits']}\n"
        f"热蓝: {analysis['hot_blue']}, 冷蓝: {analysis['cold_blue']}\n"
        f"频率候选: {json.dumps(seed, ensure_ascii=False)}\n"
        f"近12期: {json.dumps(recent, ensure_ascii=False)}\n"
        '返回: {"picks":[{"red":[1,2,3,4,5,6],"blue":8,"reason":"一句话","confidence":0.7}],"summary":"..."}\n'
        "要求: picks 恰好 2 注；尽量与候选不完全重复。"
    )

    model_results = await gather_digital_llm_json(prompt)

    def extract_items(parsed: dict) -> list[dict]:
        picks = parsed.get("picks")
        return picks if isinstance(picks, list) else []

    def build_rec(validated, conf, reason, _models):
        reds, blue = validated
        return {
            "mode": "ssq",
            "label": "AI 精选",
            "digits": reds + [blue],
            "red": reds,
            "blue": blue,
            "display": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
            "confidence": conf,
            "reason": reason,
            "bets": 1,
        }

    return fuse_ai_picks(
        model_results,
        extract_items=extract_items,
        validate_item=_validate_ssq_ai,
        build_rec=build_rec,
        limit=3,
    )


async def get_ssq_recommendations(window: int = 100, use_ai: bool = True) -> dict[str, Any]:
    from service.digital_ai import configured_digital_models, model_display_name

    window = max(20, min(int(window or 100), 100))
    draws = await fetch_ssq_history(window)
    if not draws:
        return {
            "reachable": False,
            "message": "暂时无法获取双色球官方开奖数据，无法生成频率推荐。请稍后刷新。",
            "game": "ssq",
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

    analysis = analyze_ssq(draws)
    freq_recs = build_ssq_recommendations(analysis)
    ai_picks: list[dict] = []
    configured = configured_digital_models()
    if use_ai and configured:
        ai_picks = await ai_refine_ssq(analysis, draws, freq_recs)

    # merge to 5
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

    return {
        "reachable": True,
        "message": None,
        "game": "ssq",
        "window": window,
        "sample_size": analysis["sample_size"],
        "kind": "ssq",
        "alphabets": [33, 16],
        "method": {
            "hot_weight": _HOT_WEIGHT,
            "cold_weight": _COLD_WEIGHT,
            "trend_weight": _TREND_WEIGHT,
            "ai_enabled": bool(ai_picks),
            "ai_models": model_names,
            "pick_limit": 5,
            "desc": (
                "双色球固定推荐 5 注；红蓝球分别统计历史出现概率、遗漏与近窗趋势"
                + (
                    f"，并由 {'+'.join(model_names)} 多模型精选前几注。"
                    if ai_picks and model_names
                    else ("，并由 AI 精选前几注。" if ai_picks else "。")
                )
            ),
        },
        "disclaimer": "历史频率与 AI 建议均不代表下期必然开出，请勿作为必中依据。双色球为福利彩票玩法。",
        "recommendations": merged,
        "position_stats": analysis["position_stats"],
        "overall": analysis["overall"],
        "hot_digits": analysis["hot_digits"],
        "cold_digits": analysis["cold_digits"],
        "hot_blue": analysis["hot_blue"],
        "cold_blue": analysis["cold_blue"],
        "history_preview": draws[:15],
        "latest": draws[0] if draws else None,
        "ai_enabled": bool(ai_picks),
        "ai_models": model_names,
    }
