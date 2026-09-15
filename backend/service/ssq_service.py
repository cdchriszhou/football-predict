"""福利彩票双色球 — 开奖拉取与分散参考号包（非提奖预测）。"""

from __future__ import annotations

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
    "note": (
        "红球从 01–33 中选 6 个（不重复），蓝球从 01–16 中选 1 个；每周二、四、日开奖。"
        "系统给出全号池轻加权、低重叠的分散参考号包（含最低复式与 2 胆胆拖），"
        "用于对照与试玩，不代表更高中奖率。"
    ),
    "play_types": [
        {
            "id": "single",
            "name": "单式投注",
            "prize": None,
            "prize_label": "一等奖浮动（最高1000万）",
            "desc": "6 个红球 + 1 个蓝球；一等奖需红蓝全中，另有二至六等奖。",
        },
        {
            "id": "dantuo",
            "name": "胆拖投注",
            "prize": None,
            "prize_label": "按单式拆注计奖",
            "desc": "参考形态为 2 个胆码（票面必选）+ 5 个拖码，从拖码中选 4 个凑满 6 红；注数=C(5,4)×蓝球数。",
        },
        {
            "id": "fushi",
            "name": "复式投注",
            "prize": None,
            "prize_label": "按单式拆注计奖",
            "desc": "红球选 7 个、蓝球 1 个为最低红球复式：C(7,6)×1=7 注，金额 14 元。",
        },
    ],
}

# 结构防退化阈值（组包出口硬约束）
_MAX_SINGLE_RED_SHARE = 3
_MAX_HIGH_BLUE_IN_SINGLES = 1
# 参考分与频率脱钩并压低，避免被读成「中奖概率」
_REF_SCORE_SINGLE = 0.32
_REF_SCORE_FUSHI = 0.34
_REF_SCORE_DANTUO = 0.33
_REF_SCORE_AI = 0.31

_SSQ_URLS = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
    "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice",
)

# 蓝球历史略偏 01–10；仅轻加权，选号以全池轻权抽样为主
_BLUE_LOW_MAX = 10
_BLUE_ZONE_BOOST = 0.08
_BLUE_HIGH_SHARE = 0.28
# 红球和值：用更宽分位，避免把号码强行挤进窄带（近几期常有和值 < p15）
_SUM_LO_PCT = 0.10
_SUM_HI_PCT = 0.90
# 仅极端和值才做软修正
_SUM_EXTREME_LO = 55
_SUM_EXTREME_HI = 150

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

# 降低热号主导，避免系统性弱于随机
_HOT_WEIGHT = 0.45
_COLD_WEIGHT = 0.35
_TREND_WEIGHT = 0.20


def clear_ssq_history_cache() -> None:
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


async def fetch_ssq_history(limit: int = 100, *, force_refresh: bool = False) -> list[dict]:
    limit = max(1, min(int(limit or 100), 100))
    cache_key = f"ssq:{limit}"
    now = time.monotonic()
    if force_refresh:
        _CACHE.pop(cache_key, None)
    else:
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
    red_score_map = {i + 1: red_scores[i] for i in range(33)}
    blue_score_map = {i + 1: blue_scores[i] for i in range(16)}

    # 蓝球 01–10 历史占比显著更高：在归一化分上加权，仍保留 11–16 的冷号可能
    for n in range(1, 17):
        if n <= _BLUE_LOW_MAX:
            blue_score_map[n] = min(1.0, float(blue_score_map[n]) + _BLUE_ZONE_BOOST)

    red_sums = [sum(row.get("red") or []) for row in draws if len(row.get("red") or []) == 6]
    sum_stats = _compute_sum_stats(red_sums)

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
            "zone": "low" if n <= _BLUE_LOW_MAX else "high",
            "tag": "hot" if rate >= sorted([blue_count[i] / sample for i in range(1, 17)], reverse=True)[2] else (
                "cold" if blue_gaps[n] >= sorted(blue_gaps[1:], reverse=True)[2] else "normal"
            ),
        })
    blue_stats.sort(key=lambda x: (-x["score"], -x["count"], x["digit"]))

    low_blue_hits = sum(blue_count[n] for n in range(1, _BLUE_LOW_MAX + 1))
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
        "sum_stats": sum_stats,
        "blue_zone": {
            "low_max": _BLUE_LOW_MAX,
            "low_rate": round(low_blue_hits / sample, 4) if sample else 0.0,
            "boost": _BLUE_ZONE_BOOST,
        },
        "position_stats": [red_stats, blue_stats],
        "alphabets": [33, 16],
        "overall": red_stats[:10],
    }


def _compute_sum_stats(sums: list[int]) -> dict[str, Any]:
    if not sums:
        # 理论均值约 102（6 个均匀 1–33）
        return {
            "mean": 102.0,
            "min": 21,
            "max": 168,
            "p15": 80,
            "p50": 102,
            "p85": 124,
            "target_lo": 80,
            "target_hi": 124,
            "sample": 0,
        }
    ordered = sorted(sums)
    n = len(ordered)

    def pct(p: float) -> int:
        idx = min(n - 1, max(0, int(round((n - 1) * p))))
        return int(ordered[idx])

    p15 = pct(_SUM_LO_PCT)
    p85 = pct(_SUM_HI_PCT)
    mean = sum(sums) / n
    return {
        "mean": round(mean, 1),
        "min": int(ordered[0]),
        "max": int(ordered[-1]),
        "p15": p15,
        "p50": pct(0.5),
        "p85": p85,
        "target_lo": p15,
        "target_hi": p85,
        "sample": n,
    }


def _fit_reds_to_sum(
    reds: list[int],
    pool: list[int],
    *,
    lo: int,
    hi: int,
    target: float,
) -> list[int]:
    """微调红球组合，使和值落入历史常见区间。"""
    cur = sorted(set(int(x) for x in reds if 1 <= int(x) <= 33))
    if len(cur) != 6:
        return cur
    pool_ext = [n for n in pool if 1 <= n <= 33]
    for n in range(1, 34):
        if n not in pool_ext:
            pool_ext.append(n)

    def total(xs: list[int]) -> int:
        return sum(xs)

    for _ in range(36):
        s = total(cur)
        if lo <= s <= hi:
            break
        if s < lo:
            small = min(cur)
            # 直接换入池中最大可用号，尽快抬升和值
            cand = next((n for n in sorted(pool_ext, reverse=True) if n not in cur), None)
            if cand is None or cand <= small:
                break
            cur = sorted(set(cur) - {small} | {cand})
        else:
            big = max(cur)
            cand = next((n for n in sorted(pool_ext) if n not in cur), None)
            if cand is None or cand >= big:
                break
            cur = sorted(set(cur) - {big} | {cand})

    # 已在区间内时，轻微向均值靠拢，且不得越界
    for _ in range(8):
        s = total(cur)
        if abs(s - target) <= 8:
            break
        if s < target:
            small = min(cur)
            cand = next(
                (n for n in sorted(pool_ext, reverse=True)
                 if n not in cur and n > small and s - small + n <= hi),
                None,
            )
            if cand is None:
                break
            cur = sorted(set(cur) - {small} | {cand})
        else:
            big = max(cur)
            cand = next(
                (n for n in sorted(pool_ext)
                 if n not in cur and n < big and s - big + n >= lo),
                None,
            )
            if cand is None:
                break
            cur = sorted(set(cur) - {big} | {cand})
    return cur[:6]


def _weighted_sample(
    nums: list[int],
    k: int,
    weight_fn,
    rng,
) -> list[int]:
    """无放回加权抽样。"""
    pool = list(nums)
    out: list[int] = []
    for _ in range(min(k, len(pool))):
        weights = [max(1e-6, float(weight_fn(n))) for n in pool]
        total = sum(weights)
        r = rng.random() * total
        acc = 0.0
        chosen = pool[-1]
        for n, w in zip(pool, weights):
            acc += w
            if acc >= r:
                chosen = n
                break
        out.append(chosen)
        pool.remove(chosen)
    return out


def _pick_blue_prefer_low(
    blue_ranked: list[int],
    *,
    seed: int,
    salt: int,
    allow_high: bool = False,
    force_high: bool = False,
    high_share: float | None = None,
) -> int:
    """倾向低区，但默认可按份额出高区；force_high 时必出高区。"""
    from service.digital_pick import pick_from_pool

    low = [b for b in blue_ranked if 1 <= b <= _BLUE_LOW_MAX]
    high = [b for b in blue_ranked if b > _BLUE_LOW_MAX]
    if not high:
        high = list(range(_BLUE_LOW_MAX + 1, 17))
    share = _BLUE_HIGH_SHARE if high_share is None else max(0.0, min(0.5, float(high_share)))
    roll = (seed * 31 + salt * 17) % 100
    use_high = bool(force_high) or (allow_high and roll < int(share * 100))
    if use_high and high:
        picked = pick_from_pool(high, seed, salt=salt + 101)
        return int(picked) if picked is not None else int(high[0])
    pool = low or blue_ranked or list(range(1, _BLUE_LOW_MAX + 1))
    picked = pick_from_pool(pool, seed, salt=salt)
    return int(picked) if picked is not None else 1


def _ticket_shape_ok(reds: list[int]) -> bool:
    """只挡极端怪号；允许常见双连/三连与 1–5 奇偶（贴近近窗真实开奖）。"""
    xs = sorted(set(int(x) for x in reds if 1 <= int(x) <= 33))
    if len(xs) != 6:
        return False
    odd = sum(1 for n in xs if n % 2 == 1)
    # 仅拒绝全奇/全偶；1 奇或 5 奇在真实开奖中偶见
    if odd == 0 or odd == 6:
        return False
    z1 = sum(1 for n in xs if n <= 11)
    z2 = sum(1 for n in xs if 12 <= n <= 22)
    z3 = sum(1 for n in xs if n >= 23)
    # 不允许整注落在单一大区
    if min(z1, z2, z3) == 0 and max(z1, z2, z3) >= 4:
        return False
    if max(z1, z2, z3) == 6:
        return False
    # 连号段：允许双连/三连，至多两段；禁止四连及以上或三段双连堆叠
    runs: list[int] = []
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] - xs[j] == 1:
            j += 1
        if j > i:
            runs.append(j - i + 1)
            i = j + 1
        else:
            i += 1
    if any(r >= 4 for r in runs):
        return False
    if len(runs) >= 3:
        return False
    return True


def _ticket_shape_bonus(reds: list[int]) -> float:
    """形态软分：合格加分，不合格轻罚（不硬拒，避免系统性偏离真实分布）。"""
    return 3.0 if _ticket_shape_ok(reds) else -1.0

def _zone_balanced_reds(pool: list[int], *, per_zone: int = 2) -> list[int]:
    """从候选池尽量按 01–11 / 12–22 / 23–33 各取 per_zone 个。"""
    buckets = [
        [n for n in pool if 1 <= n <= 11],
        [n for n in pool if 12 <= n <= 22],
        [n for n in pool if 23 <= n <= 33],
    ]
    out: list[int] = []
    for bucket in buckets:
        taken = 0
        for n in bucket:
            if n in out:
                continue
            out.append(n)
            taken += 1
            if taken >= per_zone:
                break
    for n in pool:
        if n not in out:
            out.append(n)
        if len(out) >= 6:
            break
    while len(out) < 6:
        for n in range(1, 34):
            if n not in out:
                out.append(n)
            if len(out) >= 6:
                break
    return sorted(out[:6])


def _pick_ssq_sets(
    analysis: dict[str, Any],
    count: int = 5,
    *,
    seed: int = 0,
    exclude: set[tuple[int, ...]] | None = None,
) -> list[tuple[list[int], int]]:
    """覆盖优先的单式：全池轻权 + 最大化并集 + 蓝球互异（整包至多 1 高区）。"""
    import random as _random

    exclude = exclude or set()
    sum_stats = analysis.get("sum_stats") or _compute_sum_stats([])
    target = float(sum_stats.get("mean") or 102)
    red_map = analysis.get("red_score_map") or {}
    blue_map = analysis.get("blue_score_map") or {}
    zone = analysis.get("blue_zone") or {}
    low_rate = float(zone.get("low_rate") or (1.0 - _BLUE_HIGH_SHARE))

    rng = _random.Random((int(seed) ^ 0x5A17) & 0xFFFFFFFF)

    def red_w(n: int) -> float:
        return 0.85 + 0.15 * float(red_map.get(n, 0.5))

    def blue_w(n: int) -> float:
        return 0.75 + 0.25 * float(blue_map.get(n, 0.5))

    picks: list[tuple[list[int], int]] = []
    used: set[tuple[int, ...]] = set()
    used_blues: set[int] = set()
    all_reds = list(range(1, 34))
    all_blues = list(range(1, 17))
    cold = list(analysis.get("cold_digits") or [])

    def too_similar(reds: list[int], *, max_share: int = 3) -> bool:
        s = set(reds)
        return any(len(s & set(prev)) >= max_share for prev, _ in picks)

    def accept(
        reds: list[int],
        blue: int,
        *,
        max_share: int = 3,
        require_shape: bool = False,
    ) -> bool:
        reds = sorted(set(int(x) for x in reds if 1 <= int(x) <= 33))
        if len(reds) != 6 or not (1 <= blue <= 16):
            return False
        # 形态默认不硬拒（由 _ticket_shape_bonus 软偏好）；极端场景可显式 require_shape
        if require_shape and not _ticket_shape_ok(reds):
            return False
        if too_similar(reds, max_share=max_share):
            return False
        key = tuple(reds + [blue])
        if key in used or key in exclude:
            return False
        used.add(key)
        used_blues.add(int(blue))
        picks.append((reds, int(blue)))
        return True
    def pick_blue(*, prefer_high: bool = False) -> int:
        high_count = sum(1 for _, b in picks if b > _BLUE_LOW_MAX)
        # 约按历史高区占比决定是否放 1 个高区蓝，避免「每包必有高区」的刻板印象
        want_high = prefer_high and high_count == 0 and rng.random() < max(0.22, min(0.35, 1.0 - low_rate))
        if high_count >= 1 or (not want_high and rng.random() < low_rate):
            cand = [b for b in all_blues if b <= _BLUE_LOW_MAX and b not in used_blues]
            if not cand:
                cand = [b for b in all_blues if b not in used_blues] or all_blues
            return int(_weighted_sample(cand, 1, blue_w, rng)[0])
        if want_high:
            cand = [b for b in all_blues if b > _BLUE_LOW_MAX and b not in used_blues]
            if cand:
                return int(_weighted_sample(cand, 1, blue_w, rng)[0])
        cand = [b for b in all_blues if b not in used_blues] or all_blues
        return int(_weighted_sample(cand, 1, blue_w, rng)[0])

    def soft_extreme(reds: list[int]) -> list[int]:
        s = sum(reds)
        if _SUM_EXTREME_LO <= s <= _SUM_EXTREME_HI:
            return reds
        fitted = _fit_reds_to_sum(
            reds, all_reds, lo=_SUM_EXTREME_LO, hi=_SUM_EXTREME_HI, target=target,
        )
        return fitted if not too_similar(fitted) else reds

    def covered() -> set[int]:
        out: set[int] = set()
        for r, _ in picks:
            out.update(r)
        return out

    def maximize_new_coverage(candidates: list[list[int]]) -> list[int] | None:
        best = None
        best_score = -1e9
        cov = covered()
        for cand in candidates:
            cset = set(cand)
            if too_similar(cand, max_share=3):
                continue
            # 形态为软偏好：不合格也可入选，避免把真实常见连号形态系统性滤掉
            score = (
                len(cset - cov) * 10
                - abs(sum(cand) - target) * 0.01
                + _ticket_shape_bonus(cand)
            )
            if score > best_score:
                best_score = score
                best = cand
        return best
    # --- 显式构造互补单式（最终常只保留 3 注，必须每注都有用）---
    # 1) 近均匀：最接近随机基线；优先形态合格，不合格也可接受
    for prefer_ok in (True, False):
        for _ in range(24):
            reds = soft_extreme(sorted(rng.sample(all_reds, 6)))
            if prefer_ok and not _ticket_shape_ok(reds):
                continue
            if accept(reds, pick_blue()):
                break
        if picks:
            break

    # 2) 避开第 1 注，偏冷/未覆盖号
    if picks:
        avoid = set(picks[0][0])
        pool2 = [n for n in (cold + all_reds) if n not in avoid] or all_reds
        cands = []
        for _ in range(30):
            cands.append(soft_extreme(_weighted_sample(pool2, 6, red_w, rng)))
        chosen = maximize_new_coverage(cands)
        if chosen and accept(chosen, pick_blue()):
            pass
        else:
            for _ in range(20):
                if accept(soft_extreme(sorted(rng.sample(all_reds, 6))), pick_blue(), max_share=4):
                    break

    # 3) 三区平衡；高区蓝按历史占比概率出现（非整包必出）
    cands = []
    for _ in range(30):
        cands.append(
            soft_extreme(
                _zone_balanced_reds(_weighted_sample(all_reds, 18, red_w, rng) + all_reds, per_zone=2)
            )
        )
    chosen = maximize_new_coverage(cands)
    if chosen and accept(chosen, pick_blue(prefer_high=True)):
        pass
    else:
        for _ in range(20):
            if accept(
                soft_extreme(_zone_balanced_reds(all_reds, per_zone=2)),
                pick_blue(prefer_high=True),
                max_share=4,
            ):
                break

    # 4+) 继续用「新增覆盖最大」补齐
    guard = 0
    while len(picks) < count and guard < 80:
        guard += 1
        cov = covered()
        prefer = [n for n in all_reds if n not in cov] or all_reds
        cands = [
            soft_extreme(_weighted_sample(prefer + all_reds, 6, red_w, rng))
            for _ in range(15)
        ]
        cands.append(soft_extreme(sorted(rng.sample(all_reds, 6))))
        chosen = maximize_new_coverage(cands)
        if chosen and accept(chosen, pick_blue()):
            continue
        reds = soft_extreme(sorted(rng.sample(all_reds, 6)))
        # 最后兜底放宽形态，保证能出满注
        if not accept(reds, pick_blue(), max_share=4):
            accept(reds, pick_blue(), max_share=4, require_shape=False)

    return picks[:count]


def build_ssq_dantuo(
    analysis: dict[str, Any],
    *,
    seed: int = 0,
    avoid_blues: set[int] | None = None,
    anchor_reds: list[int] | None = None,
) -> dict[str, Any]:
    """生成胆拖参考：固定 2 胆 + 5 拖 + 1 蓝。注数 C(5,4)=5，金额 10 元。

    若提供主推单式 anchor_reds，则 2 胆从主推中跨区抽取（与复式同属一包，避免脱节）；
    否则全池轻权 + 分属不同区间。
    """
    import random as _random
    from math import comb

    sum_stats = analysis.get("sum_stats") or _compute_sum_stats([])
    red_map = analysis.get("red_score_map") or {}
    blue_map = analysis.get("blue_score_map") or {}
    rng = _random.Random((int(seed) ^ 0xDA17) & 0xFFFFFFFF)
    avoid_blues = {int(x) for x in (avoid_blues or set())}

    all_reds = list(range(1, 34))
    anchor = sorted({int(x) for x in (anchor_reds or []) if 1 <= int(x) <= 33})

    dan: list[int] = []
    if len(anchor) >= 2:
        # 主推锚定：两胆尽量跨区，优先取自主推红球
        for _ in range(40):
            if len(dan) >= 2:
                break
            cand = [x for x in anchor if x not in dan]
            if not cand:
                break
            n = int(_weighted_sample(
                cand,
                1,
                lambda x: 0.85 + 0.15 * float(red_map.get(x, 0.5)),
                rng,
            )[0])
            if not dan:
                dan.append(n)
                continue
            z0 = 0 if dan[0] <= 11 else (1 if dan[0] <= 22 else 2)
            zn = 0 if n <= 11 else (1 if n <= 22 else 2)
            if zn != z0 or len(cand) == 1:
                dan.append(n)
        while len(dan) < 2:
            for n in anchor + all_reds:
                if n not in dan:
                    dan.append(n)
                if len(dan) >= 2:
                    break
    else:
        # 无锚定：全池轻权，强制不同区间
        for _ in range(40):
            if len(dan) >= 2:
                break
            n = int(_weighted_sample(
                [x for x in all_reds if x not in dan],
                1,
                lambda x: 0.85 + 0.15 * float(red_map.get(x, 0.5)),
                rng,
            )[0])
            if not dan:
                dan.append(n)
                continue
            z0 = 0 if dan[0] <= 11 else (1 if dan[0] <= 22 else 2)
            zn = 0 if n <= 11 else (1 if n <= 22 else 2)
            if zn != z0:
                dan.append(n)
        while len(dan) < 2:
            for n in all_reds:
                if n not in dan:
                    dan.append(n)
                if len(dan) >= 2:
                    break
    dan = sorted(dan[:2])

    # 拖码：跨区覆盖，避开胆码；优先补主推未入胆的号，再扩全池
    prefer = [n for n in anchor if n not in dan]
    pool = prefer + [n for n in all_reds if n not in dan and n not in prefer]
    tuo: list[int] = []
    for bucket in (
        [n for n in pool if 1 <= n <= 11],
        [n for n in pool if 12 <= n <= 22],
        [n for n in pool if 23 <= n <= 33],
        pool,
    ):
        bucket_w = _weighted_sample(
            [n for n in bucket if n not in tuo],
            min(2, len([n for n in bucket if n not in tuo])),
            lambda x: 0.85 + 0.15 * float(red_map.get(x, 0.5)),
            rng,
        ) if any(n not in tuo for n in bucket) else []
        for n in bucket_w:
            if n not in tuo:
                tuo.append(n)
            if len(tuo) >= 5:
                break
        if len(tuo) >= 5:
            break
    while len(tuo) < 5:
        for n in pool:
            if n not in tuo:
                tuo.append(n)
            if len(tuo) >= 5:
                break

    tuo = sorted(tuo)[:5]
    need = 6 - len(dan)
    sample_reds = sorted(dan + tuo[:need])
    s = sum(sample_reds)
    if s < _SUM_EXTREME_LO or s > _SUM_EXTREME_HI:
        sample6 = _fit_reds_to_sum(
            sample_reds,
            dan + tuo + all_reds,
            lo=_SUM_EXTREME_LO,
            hi=_SUM_EXTREME_HI,
            target=float(sum_stats.get("mean") or 102),
        )
        # 和值修正不得拆掉胆码
        tuo = sorted((set(sample6) | set(tuo)) - set(dan))
        while len(tuo) < 5:
            for n in all_reds:
                if n not in dan and n not in tuo:
                    tuo.append(n)
                if len(tuo) >= 5:
                    break
        tuo = sorted(tuo)[:5]
        sample_reds = sorted(dan + tuo[:need])

    blue_pool_cand = [b for b in range(1, 17) if b not in avoid_blues] or list(range(1, 17))
    blue = int(_weighted_sample(
        blue_pool_cand,
        1,
        lambda n: 0.75 + 0.25 * float(blue_map.get(n, 0.5)),
        rng,
    )[0])
    blue_pool = [blue]
    bets = comb(len(tuo), need) * len(blue_pool) if 0 < need <= len(tuo) else 0
    amount = bets * int(SSQ_GAME.get("price_per_bet") or 2)

    conf = _REF_SCORE_DANTUO
    display = (
        "胆 " + " ".join(_fmt_ball(x) for x in dan)
        + " | 拖 " + " ".join(_fmt_ball(x) for x in tuo)
        + " | 蓝 " + _fmt_ball(blue)
    )
    anchor_note = "胆码取自主推单式并跨区；" if len(anchor) >= 2 else "固定 2 胆（跨区轻权，非热号 Top2）；"
    return {
        "id": "pick-dantuo",
        "mode": "dantuo",
        "source": "frequency",
        "label": "胆拖参考",
        "dan": dan,
        "tuo": tuo,
        "blue": blue,
        "blue_pool": blue_pool,
        "red": sample_reds,
        "digits": sample_reds + [blue],
        "display": display,
        "confidence": conf,
        "bets": bets,
        "amount": amount,
        "reason": (
            f"{anchor_note}"
            f"拖码 5 个；注数 {bets}（C({len(tuo)},{need})），金额 {amount} 元；"
            f"样例和值 {sum(sample_reds)}。"
            "分散参考号包的一种玩法形态，不提高中奖率。"
        ),
        "sum_hint": {
            "target_lo": sum_stats.get("target_lo"),
            "target_hi": sum_stats.get("target_hi"),
            "mean": sum_stats.get("mean"),
            "sample_sum": sum(sample_reds),
        },
    }


def build_ssq_fushi(
    analysis: dict[str, Any],
    *,
    seed: int = 0,
    exclude: set[tuple[int, ...]] | None = None,
    avoid_blues: set[int] | None = None,
    anchor_reds: list[int] | None = None,
    prefer_blue: int | None = None,
) -> dict[str, Any]:
    """最低红球复式：7 红 + 1 蓝 = C(7,6)×1 = 7 注 = 14 元。

    若提供主推单式，则「主推 6 红 + 再扩 1 红」，蓝球沿用主推（典型复式扩号买法），
    避免复式与主推完全脱节。
    """
    import random as _random
    from math import comb
    from itertools import combinations

    exclude = exclude or set()
    avoid_blues = {int(x) for x in (avoid_blues or set())}
    sum_stats = analysis.get("sum_stats") or _compute_sum_stats([])
    blue_zone = analysis.get("blue_zone") or {}
    red_map = analysis.get("red_score_map") or {}
    blue_map = analysis.get("blue_score_map") or {}
    rng = _random.Random((int(seed) ^ 0xF151) & 0xFFFFFFFF)

    all_reds = list(range(1, 34))
    anchor = sorted({int(x) for x in (anchor_reds or []) if 1 <= int(x) <= 33})

    if len(anchor) >= 6:
        base6 = anchor[:6]
        outside = [n for n in all_reds if n not in base6]
        # 扩一红：轻权 + 优先补主推偏少的大区
        z_cnt = [
            sum(1 for n in base6 if 1 <= n <= 11),
            sum(1 for n in base6 if 12 <= n <= 22),
            sum(1 for n in base6 if 23 <= n <= 33),
        ]
        weak = min(range(3), key=lambda i: z_cnt[i])
        weak_bucket = [
            n for n in outside
            if (weak == 0 and n <= 11) or (weak == 1 and 12 <= n <= 22) or (weak == 2 and n >= 23)
        ] or outside
        seventh = int(_weighted_sample(
            weak_bucket,
            1,
            lambda n: 0.8 + 0.2 * float(red_map.get(n, 0.5)),
            rng,
        )[0])
        reds7 = sorted(set(base6) | {seventh})
    else:
        # 无锚定：轻权抽 12 再做三区平衡取 7
        pool = _weighted_sample(
            all_reds, 12, lambda n: 0.8 + 0.2 * float(red_map.get(n, 0.5)), rng,
        )
        base6 = _zone_balanced_reds(pool + all_reds, per_zone=2)
        seventh = next((n for n in pool + all_reds if n not in base6), None)
        reds7 = sorted(set(base6) | ({seventh} if seventh else set()))
    while len(reds7) < 7:
        for n in all_reds:
            if n not in reds7:
                reds7.append(n)
            if len(reds7) >= 7:
                break
    reds7 = sorted(reds7)[:7]

    # 蓝：锚定主推时沿用主推蓝；否则避开单式已用蓝
    if prefer_blue is not None and 1 <= int(prefer_blue) <= 16:
        blue = int(prefer_blue)
    else:
        blues = [b for b in range(1, 17) if b not in avoid_blues] or list(range(1, 17))
        blue = int(_weighted_sample(
            blues, 1, lambda n: 0.7 + 0.3 * float(blue_map.get(n, 0.5)), rng,
        )[0])
    key = tuple(reds7 + [blue])
    if key in exclude and prefer_blue is None:
        alt = [b for b in range(1, 17) if b != blue and b not in avoid_blues] or [b for b in range(1, 17) if b != blue]
        if alt:
            blue = int(_weighted_sample(alt, 1, lambda n: 0.7 + 0.3 * float(blue_map.get(n, 0.5)), rng)[0])

    bets = comb(len(reds7), 6)
    amount = bets * int(SSQ_GAME.get("price_per_bet") or 2)
    conf = _REF_SCORE_FUSHI
    target = float(sum_stats.get("mean") or 102)
    sample_reds = sorted(reds7[:6])
    best_diff = abs(sum(sample_reds) - target)
    for combo in combinations(reds7, 6):
        diff = abs(sum(combo) - target)
        if diff < best_diff:
            best_diff = diff
            sample_reds = sorted(combo)

    anchored = len(anchor) >= 6
    if prefer_blue is not None:
        blue_note = "沿用主推"
    else:
        blue_note = f"按轻权抽样（低区历史约 {float(blue_zone.get('low_rate') or 0):.0%}，非预测）"
    if anchored:
        head = f"由主推单式扩 1 红成最低复式：7 红 + 同蓝，注数 {bets}（C(7,6)），金额 {amount} 元；"
    else:
        head = f"最低红球复式：7 红 + 1 蓝，注数 {bets}（C(7,6)），金额 {amount} 元；"
    return {
        "id": "pick-fushi",
        "mode": "fushi",
        "source": "frequency",
        "label": "复式参考",
        "red": reds7,
        "blue": blue,
        "blue_pool": [blue],
        "digits": sample_reds + [blue],
        "display": (
            "复式红 " + " ".join(_fmt_ball(x) for x in reds7)
            + " + 蓝 " + _fmt_ball(blue)
        ),
        "confidence": conf,
        "bets": bets,
        "amount": amount,
        "red_sum": sum(sample_reds),
        "reason": (
            head
            + f"红球样例单式和值 {sum(sample_reds)}；蓝球{blue_note}。"
            "分散参考形态，不提高中奖率。"
        ),
    }


def _ssq_single_reds(rec: dict) -> list[int]:
    reds = rec.get("red")
    if isinstance(reds, list) and len(reds) >= 6:
        return sorted({int(x) for x in reds if 1 <= int(x) <= 33})[:6]
    digits = rec.get("digits") or []
    return sorted({int(x) for x in digits[:6] if 1 <= int(x) <= 33})[:6]


def _ssq_single_blue(rec: dict) -> int | None:
    b = rec.get("blue")
    if isinstance(b, int) and 1 <= b <= 16:
        return int(b)
    digits = rec.get("digits") or []
    if len(digits) >= 7:
        try:
            b2 = int(digits[6])
        except (TypeError, ValueError):
            return None
        if 1 <= b2 <= 16:
            return b2
    return None


def _rewrite_ssq_single(rec: dict, reds: list[int], blue: int, *, idx: int) -> dict:
    reds = sorted({int(x) for x in reds if 1 <= int(x) <= 33})[:6]
    blue = int(blue)
    red_sum = sum(reds)
    out = dict(rec)
    out.update({
        "id": f"pick-{idx}",
        "mode": "ssq",
        "digits": reds + [blue],
        "red": reds,
        "blue": blue,
        "red_sum": red_sum,
        "display": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
        "confidence": _REF_SCORE_AI if out.get("source") == "ai" else _REF_SCORE_SINGLE,
        "bets": out.get("bets") or 1,
        "amount": out.get("amount") or 2,
    })
    if out.get("source") != "ai":
        out["reason"] = (
            f"分散参考单式（和值 {red_sum}）；全号池轻加权抽样，"
            "与频率冷热脱钩展示参考度，不代表更高中奖率。"
        )
    else:
        reason = str(out.get("reason") or "AI 生成的分散参考号")
        if "中奖" not in reason and "必中" not in reason:
            reason = reason.rstrip("。") + "。AI 参考号，不提高中奖率。"
        out["reason"] = reason
    return out


def _enforce_ssq_package_invariants(
    recs: list[dict],
    analysis: dict[str, Any],
    *,
    seed: int = 0,
) -> list[dict]:
    """组包出口防退化：蓝互异、高区蓝≤1、单式重叠≤3、复式/胆拖锚定主推。"""
    import random as _random

    if not recs:
        return recs

    singles = [dict(r) for r in recs if r.get("mode") not in ("fushi", "dantuo")]
    had_fushi = any(r.get("mode") == "fushi" for r in recs)
    had_dantuo = any(r.get("mode") == "dantuo" for r in recs)
    if not singles:
        return list(recs)

    rng = _random.Random((int(seed) ^ 0xE17A) & 0xFFFFFFFF)
    all_reds = list(range(1, 34))
    all_blues = list(range(1, 17))

    def too_similar(reds: list[int], others: list[list[int]], max_share: int = _MAX_SINGLE_RED_SHARE) -> bool:
        s = set(reds)
        return any(len(s & set(o)) >= max_share for o in others)

    # --- 修复单式红球过度重叠 ---
    fixed_singles: list[dict] = []
    for i, rec in enumerate(singles):
        reds = _ssq_single_reds(rec)
        blue = _ssq_single_blue(rec) or 1
        prev = [_ssq_single_reds(x) for x in fixed_singles]
        if len(reds) != 6 or too_similar(reds, prev):
            replaced = False
            for _ in range(40):
                cand = sorted(rng.sample(all_reds, 6))
                if too_similar(cand, prev, max_share=_MAX_SINGLE_RED_SHARE):
                    continue
                reds = cand
                replaced = True
                break
            if not replaced:
                # 兜底：尽量避开已覆盖号
                covered = set().union(*(set(p) for p in prev)) if prev else set()
                prefer = [n for n in all_reds if n not in covered] or all_reds
                reds = sorted(_weighted_sample(prefer + all_reds, 6, lambda _n: 1.0, rng))
        fixed_singles.append(_rewrite_ssq_single(rec, reds, blue, idx=i + 1))

    # --- 蓝球互异 + 高区至多 1 ---
    used: set[int] = set()
    high_n = 0
    for i, rec in enumerate(fixed_singles):
        blue = _ssq_single_blue(rec) or 1
        need_new = blue in used or (blue > _BLUE_LOW_MAX and high_n >= _MAX_HIGH_BLUE_IN_SINGLES)
        if need_new:
            low_pool = [b for b in all_blues if b <= _BLUE_LOW_MAX and b not in used]
            high_pool = [b for b in all_blues if b > _BLUE_LOW_MAX and b not in used]
            allow_high = high_n < _MAX_HIGH_BLUE_IN_SINGLES and high_pool and rng.random() < _BLUE_HIGH_SHARE
            pool = (high_pool if allow_high else low_pool) or low_pool or high_pool or [
                b for b in all_blues if b not in used
            ] or all_blues
            blue = int(pool[0])
        if blue > _BLUE_LOW_MAX:
            high_n += 1
        used.add(blue)
        fixed_singles[i] = _rewrite_ssq_single(rec, _ssq_single_reds(rec), blue, idx=i + 1)

    primary = fixed_singles[0]
    anchor_reds = _ssq_single_reds(primary)
    anchor_blue = _ssq_single_blue(primary)
    out: list[dict] = list(fixed_singles)

    if had_fushi and anchor_blue is not None:
        other_blues = {
            b for b in (_ssq_single_blue(r) for r in fixed_singles[1:])
            if b is not None and b != anchor_blue
        }
        out.append(build_ssq_fushi(
            analysis,
            seed=seed,
            avoid_blues=other_blues,
            anchor_reds=anchor_reds,
            prefer_blue=anchor_blue,
        ))
    if had_dantuo:
        used_blues = {b for b in (_ssq_single_blue(r) for r in out) if b is not None}
        # 复式蓝与主推相同，胆拖需避开主推蓝
        out.append(build_ssq_dantuo(
            analysis,
            seed=seed,
            avoid_blues=used_blues,
            anchor_reds=anchor_reds,
        ))

    for i, rec in enumerate(out):
        if rec.get("mode") == "fushi":
            rec["id"] = "pick-fushi"
            rec["label"] = "复式参考"
            rec["confidence"] = _REF_SCORE_FUSHI
            continue
        if rec.get("mode") == "dantuo":
            rec["id"] = "pick-dantuo"
            rec["label"] = "胆拖参考"
            rec["confidence"] = _REF_SCORE_DANTUO
            continue
        rec["id"] = f"pick-{i + 1}"
        if rec.get("source") == "ai":
            model_label = rec.get("model_label") or "AI"
            rec["label"] = f"参考 {i + 1} · {model_label}"
            rec["confidence"] = _REF_SCORE_AI
        else:
            rec["label"] = f"参考 {i + 1}"
            rec["confidence"] = _REF_SCORE_SINGLE
    return out


def build_ssq_recommendations(
    analysis: dict[str, Any],
    *,
    seed: int = 0,
    exclude: set[tuple[int, ...]] | None = None,
    include_dantuo: bool = True,
    include_fushi: bool = True,
) -> list[dict]:
    sum_stats = analysis.get("sum_stats") or {}
    single_n = 5 - int(include_dantuo) - int(include_fushi)
    singles = _pick_ssq_sets(analysis, count=max(1, single_n), seed=seed, exclude=exclude)
    recs = []
    for i, (reds, blue) in enumerate(singles):
        red_sum = sum(reds)
        reason = (
            f"分散参考单式（和值 {red_sum}；历史常见约 "
            f"{sum_stats.get('target_lo')}–{sum_stats.get('target_hi')}）。"
            "全号池轻加权、低重叠组包；参考度≠中奖概率，不提高中奖率。"
        )
        if i == single_n - 1 and single_n >= 3:
            reason = "补覆盖/区间分散；" + reason
        recs.append({
            "id": f"pick-{i + 1}",
            "mode": "ssq",
            "source": "frequency",
            "label": f"参考 {i + 1}",
            "digits": reds + [blue],
            "red": reds,
            "blue": blue,
            "red_sum": red_sum,
            "display": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
            "confidence": _REF_SCORE_SINGLE,
            "reason": reason,
            "bets": 1,
            "amount": 2,
        })
    anchor_reds = list(recs[0]["red"]) if recs else None
    anchor_blue = int(recs[0]["blue"]) if recs else None
    if include_fushi:
        used_blues = {
            int(r["blue"]) for r in recs
            if isinstance(r.get("blue"), int) and int(r["blue"]) != anchor_blue
        }
        recs.append(build_ssq_fushi(
            analysis,
            seed=seed,
            exclude=exclude,
            avoid_blues=used_blues,
            anchor_reds=anchor_reds,
            prefer_blue=anchor_blue,
        ))
    if include_dantuo:
        used_blues = {int(r["blue"]) for r in recs if isinstance(r.get("blue"), int)}
        recs.append(build_ssq_dantuo(
            analysis,
            seed=seed,
            avoid_blues=used_blues,
            anchor_reds=anchor_reds,
        ))
    return _enforce_ssq_package_invariants(recs, analysis, seed=seed)


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
    """DeepSeek / 千问 / GLM 并行生成双色球参考号，按共识融合（非提奖）。"""
    from service.digital_ai import (
        configured_digital_models,
        fuse_ai_picks,
        gather_digital_llm_json,
    )

    if not configured_digital_models():
        return []

    recent = [{"issue": d["issue"], "result": d["result"]} for d in draws[:12]]
    seed = [
        {"display": r["display"], "confidence": r["confidence"]}
        for r in base_recs
        if r.get("mode") not in ("dantuo", "fushi")
    ][:5]
    sum_stats = analysis.get("sum_stats") or {}
    blue_zone = analysis.get("blue_zone") or {}
    prompt = (
        "你是福利彩票双色球「分散参考号」助手。根据历史形态给出购彩参考号，"
        "明确这不提高中奖率、不要声称更可能中奖或必中。严格输出 JSON。\n"
        "规则: 红球 6 个不重复整数 1-33，蓝球 1 个整数 1-16；"
        f"红球和值尽量落在 {sum_stats.get('target_lo')}–{sum_stats.get('target_hi')}（历史均值约 {sum_stats.get('mean')}）；"
        f"蓝球可覆盖 01–{_BLUE_LOW_MAX:02d} 与 11–16（近窗低区约 {float(blue_zone.get('low_rate') or 0):.0%}）。\n"
        f"样本期数: {analysis['sample_size']}\n"
        f"热红(仅形态参考): {analysis['hot_digits']}, 冷红: {analysis['cold_digits']}\n"
        f"热蓝: {analysis['hot_blue']}, 冷蓝: {analysis['cold_blue']}\n"
        f"候选参考: {json.dumps(seed, ensure_ascii=False)}\n"
        f"近12期: {json.dumps(recent, ensure_ascii=False)}\n"
        '返回: {"picks":[{"red":[1,2,3,4,5,6],"blue":8,"reason":"一句话说明分散/形态","confidence":0.3}],"summary":"..."}\n'
        "要求: picks 恰好 2 注；与候选低重叠；confidence 用 0.28–0.35 的参考度（不是中奖概率）；"
        "蓝球可覆盖低区与高区，不要两注都挤在同一小区。"
    )

    model_results = await gather_digital_llm_json(prompt)

    def extract_items(parsed: dict) -> list[dict]:
        picks = parsed.get("picks")
        return picks if isinstance(picks, list) else []

    def build_rec(validated, conf, reason, _models):
        reds, blue = validated
        # 压低并钳制，避免模型返回的高 confidence 被当成命中率
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = _REF_SCORE_AI
        conf_f = min(_REF_SCORE_AI + 0.04, max(0.28, conf_f if conf_f <= 0.4 else _REF_SCORE_AI))
        text = str(reason or "AI 分散参考号")
        if "中奖率" not in text:
            text = text.rstrip("。") + "。AI 参考号，不提高中奖率。"
        return {
            "mode": "ssq",
            "label": "AI 参考",
            "digits": reds + [blue],
            "red": reds,
            "blue": blue,
            "display": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
            "confidence": round(conf_f, 4),
            "reason": text,
            "bets": 1,
            "amount": 2,
        }

    return fuse_ai_picks(
        model_results,
        extract_items=extract_items,
        validate_item=_validate_ssq_ai,
        build_rec=build_rec,
        limit=3,
    )


async def get_ssq_recommendations(
    window: int = 100,
    use_ai: bool = True,
    *,
    force_refresh: bool = False,
    rotate: int = 0,
) -> dict[str, Any]:
    from service.digital_ai import (
        configured_digital_models,
        model_display_name,
        rec_cache_get,
        rec_cache_invalidate,
        rec_cache_set,
    )
    from service.digital_pick import period_seed

    window = max(20, min(int(window or 100), 100))
    rotate = max(0, min(int(rotate or 0), 99))
    if force_refresh:
        clear_ssq_history_cache()
        rec_cache_invalidate("ssq")

    draws = await fetch_ssq_history(window, force_refresh=force_refresh)
    latest_issue = str(draws[0]["issue"]) if draws else ""
    seed = period_seed(latest_issue, rotate)
    cache_key = f"rec:ssq:{window}:{int(bool(use_ai))}:{latest_issue}:{rotate}"
    if not force_refresh:
        cached = rec_cache_get(cache_key)
        if cached:
            cached["cached"] = True
            from service.digital_rec_store import save_primary_prediction
            save_primary_prediction(
                "ssq",
                cached.get("based_on_issue"),
                cached.get("recommendations") or [],
                rotate=rotate,
            )
            return cached

    if not draws:
        return {
            "reachable": False,
            "message": "暂时无法获取双色球官方开奖数据，无法生成参考号。请稍后刷新。",
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
            "rotate": rotate,
            "based_on_issue": None,
        }

    exclude: set[tuple[int, ...]] = set()
    if draws and isinstance(draws[0].get("digits"), list) and len(draws[0]["digits"]) >= 7:
        exclude.add(tuple(int(x) for x in draws[0]["digits"][:7]))

    analysis = analyze_ssq(draws)
    freq_recs = build_ssq_recommendations(
        analysis, seed=seed, exclude=exclude, include_dantuo=True, include_fushi=True,
    )
    ai_picks: list[dict] = []
    configured = configured_digital_models()
    if use_ai and configured:
        ai_picks = await ai_refine_ssq(analysis, draws, freq_recs)

    fushi_rec = next((r for r in freq_recs if r.get("mode") == "fushi"), None)
    dantuo_rec = next((r for r in freq_recs if r.get("mode") == "dantuo"), None)
    singles = [r for r in freq_recs if r.get("mode") not in ("dantuo", "fushi")]

    # AI 参考号只并入单式，且不得与已有单式红球高度重叠；最后附带复式与胆拖
    merged: list[dict] = []
    seen: set[tuple] = set()

    def reds_of(rec: dict) -> set[int]:
        if rec.get("mode") == "fushi":
            return {int(x) for x in (rec.get("red") or [])}
        digits = rec.get("digits") or rec.get("red") or []
        try:
            return {int(x) for x in list(digits)[:6]}
        except (TypeError, ValueError):
            return set()

    for rec in list(ai_picks) + singles:
        key = tuple(rec.get("digits") or [])
        if not key or key in seen:
            continue
        rset = reds_of(rec)
        if any(len(rset & reds_of(m)) >= 4 for m in merged if m.get("mode") == "ssq"):
            continue
        seen.add(key)
        merged.append(rec)
        if len([m for m in merged if m.get("mode") == "ssq"]) >= 3:
            break
    # 若 AI 过滤后单式不足，用频率单式补齐
    if len([m for m in merged if m.get("mode") == "ssq"]) < 3:
        for rec in singles:
            key = tuple(rec.get("digits") or [])
            if not key or key in seen:
                continue
            rset = reds_of(rec)
            if any(len(rset & reds_of(m)) >= 4 for m in merged if m.get("mode") == "ssq"):
                continue
            seen.add(key)
            merged.append(rec)
            if len([m for m in merged if m.get("mode") == "ssq"]) >= 3:
                break

    # 挂上复式/胆拖后统一结构防退化（按最终主推重锚定）
    if fushi_rec:
        merged.append(fushi_rec)
    if dantuo_rec:
        merged.append(dantuo_rec)
    merged = _enforce_ssq_package_invariants(merged, analysis, seed=seed)
    fushi_rec = next((r for r in merged if r.get("mode") == "fushi"), None)
    dantuo_rec = next((r for r in merged if r.get("mode") == "dantuo"), None)

    model_names = sorted({
        model_display_name(m)
        for r in ai_picks
        for m in (r.get("models") or [])
    })

    sum_stats = analysis.get("sum_stats") or {}
    blue_zone = analysis.get("blue_zone") or {}
    payload = {
        "reachable": True,
        "message": None,
        "game": "ssq",
        "window": window,
        "sample_size": analysis["sample_size"],
        "kind": "ssq",
        "alphabets": [33, 16],
        "based_on_issue": latest_issue or None,
        "rotate": rotate,
        "method": {
            "hot_weight": _HOT_WEIGHT,
            "cold_weight": _COLD_WEIGHT,
            "trend_weight": _TREND_WEIGHT,
            "ai_enabled": bool(ai_picks),
            "ai_models": model_names,
            "pick_limit": 5,
            "period_seed": True,
            "sum_constraint": "extreme_only",
            "blue_zone_prefer": f"01-{_BLUE_LOW_MAX:02d}",
            "dantuo": True,
            "fushi": True,
            "reference_only": True,
            "structure_guard": True,
            "desc": (
                f"基于第 {latest_issue} 期后生成分散参考号包（非提奖预测）："
                f"红球全号池轻加权+低重叠；极端和值才软修正（常见带约 "
                f"{sum_stats.get('target_lo')}–{sum_stats.get('target_hi')}）；"
                f"蓝球互异且整包至多 1 个高区；形态软偏好；"
                "复式由主推扩 1 红同蓝、胆拖胆码锚定主推；参考度≠中奖概率"
                + (f"；换号批次 {rotate}" if rotate else "")
                + (
                    f"；含 {'+'.join(model_names)} 参考单式。"
                    if ai_picks and model_names
                    else ("；含 AI 参考单式。" if ai_picks else "。可点「换一批」换号。")
                )
            ),
        },
        "disclaimer": (
            "本页为分散参考号包，历史频率与 AI 均不提高中奖率，也不代表下期更可能开出；"
            "请勿作为必中或投注依据。双色球为福利彩票玩法。"
        ),
        "recommendations": merged,
        "fushi": fushi_rec,
        "dantuo": dantuo_rec,
        "sum_stats": sum_stats,
        "blue_zone": blue_zone,
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
        "cached": False,
    }
    from service.digital_rec_store import save_primary_prediction
    # 完整保存 3 单式 + 复式 + 胆拖，供「近期开奖」对照
    save_primary_prediction(
        "ssq",
        latest_issue or None,
        merged,
        rotate=rotate,
    )
    rec_cache_set(cache_key, payload)
    return payload
