"""福利彩票双色球 — 开奖拉取、频率推荐与可选 AI 精选。"""

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
    "note": "红球从 01–33 中选 6 个（不重复），蓝球从 01–16 中选 1 个；每周二、四、日开奖。推荐参考历史红球和值与蓝球 01–10，并提供最低金额复式（7红+1蓝）与 2 胆胆拖参考。",
    "play_types": [
        {
            "id": "single",
            "name": "单式投注",
            "prize": None,
            "prize_label": "一等奖浮动（最高1000万）",
            "desc": "6 个红球 + 1 个蓝球全部命中为一等奖；另有二至六等奖。",
        },
        {
            "id": "dantuo",
            "name": "胆拖投注",
            "prize": None,
            "prize_label": "按单式拆注计奖",
            "desc": "红球固定 2 个胆码（必出）+ 拖码选满 6 个；注数=C(拖码数, 4)×蓝球数。",
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

_SSQ_URLS = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
    "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice",
)

# 蓝球历史更常落在 01–10；评分轻加权，选号保留约 1/4 高区多样性
_BLUE_LOW_MAX = 10
_BLUE_ZONE_BOOST = 0.12
_BLUE_HIGH_SHARE = 0.28  # 约等于历史 11–16 占比，避免五注全锁低区
# 红球和值：落在历史分位区间内更常见
_SUM_LO_PCT = 0.15
_SUM_HI_PCT = 0.85

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


def _pick_blue_prefer_low(
    blue_ranked: list[int],
    *,
    seed: int,
    salt: int,
    allow_high: bool = False,
    force_high: bool = False,
    high_share: float | None = None,
) -> int:
    """倾向 01–10，但按 high_share / force_high 保留 11–16，避免整包锁死低区。"""
    from service.digital_pick import pick_from_pool

    low = [b for b in blue_ranked if 1 <= b <= _BLUE_LOW_MAX]
    high = [b for b in blue_ranked if b > _BLUE_LOW_MAX]
    if not high:
        high = list(range(_BLUE_LOW_MAX + 1, 17))
    share = _BLUE_HIGH_SHARE if high_share is None else max(0.0, min(0.6, float(high_share)))
    # force_high 必出高区；否则按份额掷骰（约等于历史 11–16 占比）
    roll = (seed * 31 + salt * 17) % 100
    use_high = bool(force_high) or (allow_high and roll < int(share * 100)) or (
        (not allow_high) and roll < int(share * 50)
    )
    if use_high and high:
        picked = pick_from_pool(high, seed, salt=salt + 101)
        return int(picked) if picked is not None else int(high[0])
    pool = low or blue_ranked or list(range(1, _BLUE_LOW_MAX + 1))
    picked = pick_from_pool(pool, seed, salt=salt)
    return int(picked) if picked is not None else 1


def _jaccard_red(a: list[int], b: list[int]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


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
    from service.digital_pick import rotate_ranked

    exclude = exclude or set()
    sum_stats = analysis.get("sum_stats") or _compute_sum_stats([])
    lo = int(sum_stats.get("target_lo") or 80)
    hi = int(sum_stats.get("target_hi") or 124)
    target = float(sum_stats.get("mean") or 102)

    red_ranked = rotate_ranked(
        [r["digit"] for r in analysis["red_stats"]], seed, top_k=10, salt=3,
    )
    blue_ranked = rotate_ranked(
        [b["digit"] for b in analysis["blue_stats"]], seed, top_k=6, salt=11,
    )
    cold_red = rotate_ranked(list(analysis["cold_digits"]), seed, top_k=6, salt=19)

    picks: list[tuple[list[int], int]] = []
    used: set[tuple[int, ...]] = set()
    used_blues: set[int] = set()

    def pick_blue(**kwargs) -> int:
        ranked = [b for b in blue_ranked if b not in used_blues] or list(blue_ranked)
        return _pick_blue_prefer_low(ranked, **kwargs)

    def add(reds: list[int], blue: int, *, fit_sum: bool = True) -> None:
        reds = sorted(set(int(x) for x in reds))
        if fit_sum:
            reds = _fit_reds_to_sum(reds, red_ranked + cold_red, lo=lo, hi=hi, target=target)
        reds = sorted(set(reds))
        if len(reds) != 6 or not (1 <= blue <= 16):
            return
        key = tuple(reds + [blue])
        if key in used or key in exclude:
            return
        used.add(key)
        used_blues.add(int(blue))
        picks.append((reds, blue))

    # 高区占比：用样本统计；缺省约 28%
    zone = analysis.get("blue_zone") or {}
    low_rate = float(zone.get("low_rate") or (1.0 - _BLUE_HIGH_SHARE))
    high_share = max(0.18, min(0.45, 1.0 - low_rate))

    # 1 主推：热红 + 倾向低区蓝，和值拟合
    add(red_ranked[:6], pick_blue(seed=seed, salt=1, high_share=high_share * 0.5,
    ))
    # 2 次热红 + 另一蓝（可高区）
    add(red_ranked[1:7], pick_blue(seed=seed, salt=2, allow_high=True, high_share=high_share,
    ))
    # 3 热红混冷红 — 固定一注高区蓝，避免最终只取 3 单式时整包锁死 01–10
    mix = sorted(set(red_ranked[:4] + cold_red[:2]))[:6]
    if len(mix) < 6:
        for n in red_ranked:
            if n not in mix:
                mix.append(n)
            if len(mix) >= 6:
                break
    add(
        sorted(mix[:6]),
        pick_blue(seed=seed, salt=3, force_high=True),
    )
    # 4 冷号回补
    add(
        sorted(cold_red[:6]),
        pick_blue(seed=seed, salt=4, allow_high=True, high_share=high_share,
        ),
        fit_sum=True,
    )
    # 5 奇偶均衡
    odd = [n for n in red_ranked if n % 2 == 1]
    even = [n for n in red_ranked if n % 2 == 0]
    bal = sorted((odd[:3] + even[:3])[:6])
    add(bal, pick_blue(seed=seed, salt=5, allow_high=True, high_share=high_share,
    ))

    offset = 2
    while len(picks) < count and offset < 24:
        chunk = red_ranked[offset:offset + 6]
        if len(chunk) < 6:
            chunk = (red_ranked + cold_red + list(range(1, 34)))[:6]
        add(
            chunk,
            pick_blue(
                seed=seed,
                salt=10 + offset,
                allow_high=True,
                force_high=(offset % 3 == 0),
                high_share=high_share,
            ),
        )
        offset += 1

    return picks[:count]


def build_ssq_dantuo(
    analysis: dict[str, Any],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    """生成胆拖参考：固定 2 胆 + 5 拖 + 1 蓝（蓝优先 01–10）。注数 C(5,4)=5，金额 10 元。"""
    from math import comb
    from service.digital_pick import rotate_ranked

    sum_stats = analysis.get("sum_stats") or _compute_sum_stats([])
    red_ranked = rotate_ranked(
        [r["digit"] for r in analysis["red_stats"]], seed, top_k=12, salt=41,
    )
    blue_ranked = rotate_ranked(
        [b["digit"] for b in analysis["blue_stats"]], seed, top_k=6, salt=43,
    )
    cold = rotate_ranked(list(analysis["cold_digits"]), seed, top_k=6, salt=47)

    dan_candidates = red_ranked[:8]
    dan: list[int] = []
    # 两胆尽量分属不同区间，提高覆盖
    for n in dan_candidates:
        if not dan:
            dan.append(n)
            continue
        z0 = 0 if dan[0] <= 11 else (1 if dan[0] <= 22 else 2)
        zn = 0 if n <= 11 else (1 if n <= 22 else 2)
        if zn != z0:
            dan.append(n)
            break
    if len(dan) < 2:
        for n in dan_candidates + cold:
            if n not in dan:
                dan.append(n)
            if len(dan) >= 2:
                break
    dan = sorted(dan[:2])
    tuo_pool = [n for n in _zone_balanced_reds(red_ranked[2:] + cold + red_ranked, per_zone=2) if n not in dan]
    # zone_balanced returns 6; we need 5 tuo — rebuild
    tuo_pool = [n for n in red_ranked + cold + list(range(1, 34)) if n not in dan]
    # 拖码也尽量跨区
    tuo = []
    for bucket in (
        [n for n in tuo_pool if 1 <= n <= 11],
        [n for n in tuo_pool if 12 <= n <= 22],
        [n for n in tuo_pool if 23 <= n <= 33],
        tuo_pool,
    ):
        for n in bucket:
            if n not in tuo and n not in dan:
                tuo.append(n)
            if len(tuo) >= 5:
                break
        if len(tuo) >= 5:
            break
    while len(tuo) < 5:
        for n in range(1, 34):
            if n not in dan and n not in tuo:
                tuo.append(n)
            if len(tuo) >= 5:
                break

    # 用「胆 + 拖中 4 个」做和值拟合，再回写拖码（胆码锁定）
    need = 6 - len(dan)  # 4
    sample6 = _fit_reds_to_sum(
        dan + tuo[:need],
        dan + tuo,
        lo=int(sum_stats.get("target_lo") or 80),
        hi=int(sum_stats.get("target_hi") or 124),
        target=float(sum_stats.get("mean") or 102),
    )
    tuo = sorted((set(sample6) | set(tuo)) - set(dan))
    while len(tuo) < 5:
        for n in red_ranked + list(range(1, 34)):
            if n not in dan and n not in tuo:
                tuo.append(n)
            if len(tuo) >= 5:
                break
    tuo = sorted(tuo)[:5]

    blue = _pick_blue_prefer_low(blue_ranked, seed=seed, salt=49)
    blue_pool = [blue]
    bets = comb(len(tuo), need) * len(blue_pool) if 0 < need <= len(tuo) else 0
    amount = bets * int(SSQ_GAME.get("price_per_bet") or 2)

    conf = (
        sum(analysis["red_score_map"].get(n, 0.5) for n in dan) / max(1, len(dan))
        + sum(analysis["red_score_map"].get(n, 0.5) for n in tuo) / max(1, len(tuo))
        + analysis["blue_score_map"].get(blue, 0.5)
    ) / 3

    display = (
        "胆 " + " ".join(_fmt_ball(x) for x in dan)
        + " | 拖 " + " ".join(_fmt_ball(x) for x in tuo)
        + " | 蓝 " + _fmt_ball(blue)
    )
    sample_reds = sorted(dan + tuo[:need])
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
        "confidence": round(conf, 4),
        "bets": bets,
        "amount": amount,
        "reason": (
            f"固定 2 胆 + 5 拖；从拖码选 {need} 个凑满 6 红，"
            f"注数 {bets}（C({len(tuo)},{need})），金额 {amount} 元；"
            f"和值倾向 {sum_stats.get('target_lo')}–{sum_stats.get('target_hi')} "
            f"（均值约 {sum_stats.get('mean')}）；"
            f"蓝球倾向 01–{_BLUE_LOW_MAX:02d}，并保留高区。"
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
) -> dict[str, Any]:
    """最低红球复式：7 红 + 1 蓝 = C(7,6)×1 = 7 注 = 14 元。"""
    from math import comb
    from service.digital_pick import rotate_ranked

    exclude = exclude or set()
    sum_stats = analysis.get("sum_stats") or _compute_sum_stats([])
    blue_zone = analysis.get("blue_zone") or {}
    red_ranked = rotate_ranked(
        [r["digit"] for r in analysis["red_stats"]], seed, top_k=16, salt=61,
    )
    blue_ranked = rotate_ranked(
        [b["digit"] for b in analysis["blue_stats"]], seed, top_k=8, salt=67,
    )
    cold = rotate_ranked(list(analysis["cold_digits"]), seed, top_k=6, salt=71)

    # 7 红：三区尽量覆盖，再和值微调其中一注样例
    base6 = _zone_balanced_reds(red_ranked + cold, per_zone=2)
    base6 = _fit_reds_to_sum(
        base6,
        red_ranked + cold,
        lo=int(sum_stats.get("target_lo") or 80) - 8,
        hi=int(sum_stats.get("target_hi") or 124) + 8,
        target=float(sum_stats.get("mean") or 102),
    )
    seventh = next(
        (n for n in red_ranked + cold + list(range(1, 34)) if n not in base6),
        None,
    )
    reds7 = sorted(set(base6) | ({seventh} if seventh else set()))
    while len(reds7) < 7:
        for n in range(1, 34):
            if n not in reds7:
                reds7.append(n)
            if len(reds7) >= 7:
                break
    reds7 = sorted(reds7)[:7]

    blue = _pick_blue_prefer_low(
        blue_ranked, seed=seed, salt=73, allow_high=True, force_high=((seed + 73) % 3 == 0),
    )
    # 避免与最新开奖整注完全相同
    key = tuple(reds7 + [blue])
    if key in exclude:
        alt_blue = _pick_blue_prefer_low(
            [b for b in blue_ranked if b != blue] or blue_ranked,
            seed=seed,
            salt=79,
        )
        blue = alt_blue

    bets = comb(len(reds7), 6)  # 7
    amount = bets * int(SSQ_GAME.get("price_per_bet") or 2)
    conf = (
        sum(analysis["red_score_map"].get(n, 0.5) for n in reds7) / len(reds7)
        + analysis["blue_score_map"].get(blue, 0.5)
    ) / 2
    # 样例单式：和值最接近目标的一注
    target = float(sum_stats.get("mean") or 102)
    sample_reds = sorted(reds7[:6])
    best_diff = abs(sum(sample_reds) - target)
    from itertools import combinations
    for combo in combinations(reds7, 6):
        diff = abs(sum(combo) - target)
        if diff < best_diff:
            best_diff = diff
            sample_reds = sorted(combo)

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
        "confidence": round(conf, 4),
        "bets": bets,
        "amount": amount,
        "red_sum": sum(sample_reds),
        "reason": (
            f"最低红球复式：7 红 + 1 蓝，注数 {bets}（C(7,6)），金额 {amount} 元；"
            f"红球和值参考 {sum_stats.get('target_lo')}–{sum_stats.get('target_hi')} "
            f"（样例单式和值 {sum(sample_reds)}）；"
            f"蓝球倾向 01–{_BLUE_LOW_MAX:02d}，并保留 11–16 多样性"
            f"（近窗约 {float(blue_zone.get('low_rate') or 0):.0%}）。"
        ),
    }


def build_ssq_recommendations(
    analysis: dict[str, Any],
    *,
    seed: int = 0,
    exclude: set[tuple[int, ...]] | None = None,
    include_dantuo: bool = True,
    include_fushi: bool = True,
) -> list[dict]:
    red_map = analysis["red_score_map"]
    blue_map = analysis["blue_score_map"]
    sum_stats = analysis.get("sum_stats") or {}
    blue_zone = analysis.get("blue_zone") or {}
    single_n = 5 - int(include_dantuo) - int(include_fushi)
    singles = _pick_ssq_sets(analysis, count=max(1, single_n), seed=seed, exclude=exclude)
    recs = []
    for i, (reds, blue) in enumerate(singles):
        conf = (sum(red_map[n] for n in reds) / 6 + blue_map[blue]) / 2
        red_sum = sum(reds)
        reason = (
            f"红球频率/遗漏/趋势 + 和值约束（本注 {red_sum}，"
            f"目标 {sum_stats.get('target_lo')}–{sum_stats.get('target_hi')}，"
            f"均值约 {sum_stats.get('mean')}）；"
            f"蓝球倾向 01–{_BLUE_LOW_MAX:02d}（保留高区）"
            f"（历史约 {float(blue_zone.get('low_rate') or 0):.0%}）"
        )
        if i == single_n - 1 and single_n >= 3:
            reason = "冷号回补 + 和值拟合；蓝球仍优先低区 " + reason
        recs.append({
            "id": f"pick-{i + 1}",
            "mode": "ssq",
            "source": "frequency",
            "label": f"推荐 {i + 1}",
            "digits": reds + [blue],
            "red": reds,
            "blue": blue,
            "red_sum": red_sum,
            "display": " ".join(_fmt_ball(x) for x in reds) + " + " + _fmt_ball(blue),
            "confidence": round(conf, 4),
            "reason": reason,
            "bets": 1,
            "amount": 2,
        })
    if include_fushi:
        recs.append(build_ssq_fushi(analysis, seed=seed, exclude=exclude))
    if include_dantuo:
        recs.append(build_ssq_dantuo(analysis, seed=seed))
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
    seed = [
        {"display": r["display"], "confidence": r["confidence"]}
        for r in base_recs
        if r.get("mode") not in ("dantuo", "fushi")
    ][:5]
    sum_stats = analysis.get("sum_stats") or {}
    blue_zone = analysis.get("blue_zone") or {}
    prompt = (
        "你是福利彩票双色球选号分析助手。根据历史频率、红球和值分布与蓝球区间给出购彩参考号，不要声称必中。严格输出 JSON。\n"
        "规则: 红球 6 个不重复整数 1-33，蓝球 1 个整数 1-16；"
        f"红球和值尽量落在 {sum_stats.get('target_lo')}–{sum_stats.get('target_hi')}（历史均值约 {sum_stats.get('mean')}）；"
        f"蓝球倾向 01–{_BLUE_LOW_MAX:02d}，但不要排除 11–16（近窗低区约 {float(blue_zone.get('low_rate') or 0):.0%}）。\n"
        f"样本期数: {analysis['sample_size']}\n"
        f"热红: {analysis['hot_digits']}, 冷红: {analysis['cold_digits']}\n"
        f"热蓝: {analysis['hot_blue']}, 冷蓝: {analysis['cold_blue']}\n"
        f"频率候选: {json.dumps(seed, ensure_ascii=False)}\n"
        f"近12期: {json.dumps(recent, ensure_ascii=False)}\n"
        '返回: {"picks":[{"red":[1,2,3,4,5,6],"blue":8,"reason":"一句话","confidence":0.7}],"summary":"..."}\n'
        "要求: picks 恰好 2 注；尽量与候选不完全重复；蓝球可覆盖低区与高区，不要两注都挤在同一小区。"
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

    # AI 精选只并入单式，最后固定附带复式与胆拖参考
    merged: list[dict] = []
    seen: set[tuple] = set()
    for rec in list(ai_picks) + singles:
        key = tuple(rec.get("digits") or [])
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(rec)
        if len(merged) >= 3:
            break
    if fushi_rec:
        merged.append(fushi_rec)
    if dantuo_rec:
        merged.append(dantuo_rec)
    for i, rec in enumerate(merged):
        if rec.get("mode") == "fushi":
            rec["id"] = "pick-fushi"
            rec["label"] = "复式参考"
            continue
        if rec.get("mode") == "dantuo":
            rec["id"] = "pick-dantuo"
            rec["label"] = "胆拖参考"
            continue
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
            "sum_constraint": True,
            "blue_zone_prefer": f"01-{_BLUE_LOW_MAX:02d}",
            "dantuo": True,
            "fushi": True,
            "desc": (
                f"基于第 {latest_issue} 期后统计；红球参考历史和值"
                f"（约 {sum_stats.get('target_lo')}–{sum_stats.get('target_hi')}，"
                f"均值 {sum_stats.get('mean')}）；"
                f"蓝球倾向 01–{_BLUE_LOW_MAX:02d}"
                f"（近窗约 {float(blue_zone.get('low_rate') or 0):.0%}，保留高区多样性）；"
                "并给出最低金额复式（7红+1蓝）与 2 胆胆拖参考"
                + (f"；换号批次 {rotate}" if rotate else "")
                + (
                    f"；并由 {'+'.join(model_names)} 精选部分单式。"
                    if ai_picks and model_names
                    else ("；并由 AI 精选部分单式。" if ai_picks else "。可点「换一批」换号。")
                )
            ),
        },
        "disclaimer": "历史频率、和值区间与 AI 建议均不代表下期必然开出，请勿作为必中依据。双色球为福利彩票玩法。",
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
    save_primary_prediction(
        "ssq",
        latest_issue or None,
        [r for r in merged if r.get("mode") not in ("dantuo", "fushi")] or merged,
        rotate=rotate,
    )
    rec_cache_set(cache_key, payload)
    return payload
