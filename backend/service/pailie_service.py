"""体彩排列3 / 排列5 / 七星彩 — 开奖拉取、频率推荐与可选 AI 精选。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import httpx

from utils.http_client import sporttery_proxy_attempts
from utils.logger import logger

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
        "title": "体彩排列3 / 排列5 / 七星彩",
        "disclaimer": (
            "本模块仅提供玩法说明、历史频率统计、概率参考与 AI 选号辅助，不提供购彩下单；"
            "历史频率与 AI 建议均不能保证未来开奖结果，请理性投注并到官方渠道购买。"
        ),
        "games": [PL3_GAME, PL5_GAME, QXC_GAME],
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
    # 紧凑串如 12345614 / 123456+14 已拆；若仍是单 token 且为长数字则按位拆前区
    if len(tokens) == 1 and tokens[0].isdigit() and len(tokens[0]) >= need:
        compact = tokens[0]
        if game_id == "qxc" and len(compact) >= 7:
            # 末位可能是两位数 10-14
            front = compact[:6]
            back = compact[6:]
            tokens = list(front) + [back]
        elif len(compact) >= need:
            tokens = list(compact[:need])

    parsed: list[int] = []
    for i, tok in enumerate(tokens):
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
    alphabets = analysis["alphabets"]
    n_pos = len(alphabets)
    scores = analysis["position_scores"]
    directs = _pick_direct_numbers(scores, alphabets, count=5)
    recs: list[dict] = []

    for i, nums in enumerate(directs):
        conf = sum(scores[p][nums[p]] for p in range(n_pos)) / n_pos
        recs.append({
            "id": f"direct-{i + 1}",
            "mode": "direct",
            "source": "frequency",
            "label": "主推直选" if i == 0 else f"备选直选 {i}",
            "digits": nums,
            "display": " ".join(str(x) for x in nums),
            "confidence": round(conf, 4),
            "reason": "各位历史出现率 + 遗漏 + 近窗趋势综合得分",
            "bets": 1,
        })

    cold_pick = _cold_pick(analysis)
    if tuple(cold_pick) not in {tuple(r["digits"]) for r in recs}:
        recs.append({
            "id": "cold-direct",
            "mode": "direct",
            "source": "frequency",
            "label": "冷号回补直选",
            "digits": cold_pick,
            "display": " ".join(str(x) for x in cold_pick),
            "confidence": round(sum(scores[p][cold_pick[p]] for p in range(n_pos)) / n_pos, 4),
            "reason": "各位遗漏期数偏大的号码，作均衡参考",
            "bets": 1,
        })

    if game_id == "pl3":
        hot = analysis["hot_digits"]
        g3 = sorted(hot[:2])
        if len(g3) >= 2:
            recs.append({
                "id": "group3-1",
                "mode": "group3",
                "source": "frequency",
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
        g6 = sorted(hot[:3])
        if len(g6) >= 3:
            recs.append({
                "id": "group6-1",
                "mode": "group6",
                "source": "frequency",
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

    return recs


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
    """可选 DeepSeek 精选：在频率候选上再给 1–3 注 AI 号。无密钥或失败则跳过。"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return []

    from config import DEEPSEEK_API_URL
    from llm.deepseek_client import _call_api, _parse_llm_json

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
        "要求: picks 1~3 注；digits 长度与位数一致；七星彩末位可为0-14。"
    )

    try:
        data = await _call_api(
            api_key,
            DEEPSEEK_API_URL,
            "deepseek-chat",
            prompt,
            temperature=0.4,
            max_tokens=800,
            json_mode=True,
        )
        content = (data or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_llm_json(content) or {}
    except Exception as e:
        logger.warning("pailie AI refine failed [%s]: %s", game_id, e)
        return []

    picks = parsed.get("picks") if isinstance(parsed, dict) else None
    if not isinstance(picks, list):
        return []

    out: list[dict] = []
    for i, item in enumerate(picks[:3]):
        if not isinstance(item, dict):
            continue
        digits = _validate_ai_digits(item.get("digits") or [], alphabets)
        if not digits:
            continue
        conf = item.get("confidence")
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = 0.6
        conf_f = max(0.0, min(1.0, conf_f))
        reason = str(item.get("reason") or parsed.get("summary") or "AI 结合频率与走势精选").strip()[:120]
        out.append({
            "id": f"ai-{i + 1}",
            "mode": "direct",
            "source": "ai",
            "label": "AI 精选" if i == 0 else f"AI 备选 {i}",
            "digits": digits,
            "display": " ".join(str(x) for x in digits),
            "confidence": round(conf_f, 4),
            "reason": reason,
            "bets": 1,
        })
    return out


async def get_recommendations(
    game_id: str,
    window: int = 100,
    use_ai: bool = True,
) -> dict[str, Any]:
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
            "ai_enabled": False,
        }

    alphabets = GAME_SPECS[game_id]["alphabets"]
    analysis = _analyze_draws(draws, alphabets)
    recs = _build_recommendations(game_id, draws, analysis)

    ai_picks: list[dict] = []
    ai_enabled = bool(os.getenv("DEEPSEEK_API_KEY", "")) and use_ai
    if ai_enabled:
        ai_picks = await _ai_refine_picks(game_id, analysis, draws, recs)
        # AI 精选插到频率主推之后
        if ai_picks:
            head = [r for r in recs if r["id"] == "direct-1"]
            rest = [r for r in recs if r["id"] != "direct-1"]
            recs = head + ai_picks + rest

    return {
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
            "desc": (
                "历史样本按位统计出现概率与遗漏，叠加近窗趋势；"
                + ("已用 AI 结合统计结果精选参考号。" if ai_picks else "AI 未启用或暂不可用，仅展示频率推荐。")
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
    }
