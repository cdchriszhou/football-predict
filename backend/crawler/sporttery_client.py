"""
China Sports Lottery (体彩竞彩足球) official API client.

Primary endpoint: getMatchCalculatorV1.qry — on-sale matches with full odds
(SPF / RQSPF / CRS / HAFU / TTG).
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx

from config import SPORTTERY_PLAYWRIGHT_FALLBACK
from utils.http_client import get_crawler_proxy, socks_proxy_supported, sporttery_proxy_attempts
from utils.logger import logger

WAF_BLOCKED_HINT = (
    "sporttery.cn HTTP 567 (WAF 拦截)。"
    "国内部署：不要设置 SPORTTERY_PROXY，添加 SPORTTERY_DIRECT=true，"
    "并确保体彩走直连（Clash 规则 sporttery.cn → DIRECT，勿经海外节点）；"
    "可暂时注释 CRAWLER_PROXY 后重启测试。"
    "海外部署：设置 SPORTTERY_PROXY 并将 sporttery.cn 指向中国大陆节点。"
)

from data.club_sporttery_aliases import CLUB_SPORTTERY_ALIASES

SPORTTERY_CALCULATOR_API = (
    "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"
)

# Sporttery display names → canonical names used in our match DB
SPORTTERY_TEAM_ALIASES: dict[str, str] = {
    "沙特": "沙特阿拉伯",
    "沙特阿拉伯": "沙特阿拉伯",
    "韩国": "韩国",
    "美国": "美国",
    "墨西哥": "墨西哥",
    "日本": "日本",
    "英格兰": "英格兰",
    "法国": "法国",
    "德国": "德国",
    "西班牙": "西班牙",
    "葡萄牙": "葡萄牙",
    "荷兰": "荷兰",
    "比利时": "比利时",
    "阿根廷": "阿根廷",
    "巴西": "巴西",
    "乌拉圭": "乌拉圭",
    "哥伦比亚": "哥伦比亚",
    "厄瓜多尔": "厄瓜多尔",
    "科特迪瓦": "科特迪瓦",
    "塞内加尔": "塞内加尔",
    "摩洛哥": "摩洛哥",
    "突尼斯": "突尼斯",
    "阿尔及利亚": "阿尔及利亚",
    "加纳": "加纳",
    "喀麦隆": "喀麦隆",
    "埃及": "埃及",
    "南非": "南非",
    "澳大利亚": "澳大利亚",
    "新西兰": "新西兰",
    "伊朗": "伊朗",
    "伊拉克": "伊拉克",
    "约旦": "约旦",
    "卡塔尔": "卡塔尔",
    "乌兹别克斯坦": "乌兹别克斯坦",
    "加拿大": "加拿大",
    "哥斯达黎加": "哥斯达黎加",
    "巴拿马": "巴拿马",
    "海地": "海地",
    "库拉索": "库拉索",
    "瑞士": "瑞士",
    "奥地利": "奥地利",
    "克罗地亚": "克罗地亚",
    "苏格兰": "苏格兰",
    "捷克": "捷克",
    "土耳其": "土耳其",
    "挪威": "挪威",
    "瑞典": "瑞典",
    "波兰": "波兰",
    "乌克兰": "乌克兰",
    "威尔士": "威尔士",
    "波黑": "波黑",
    "塞尔维亚": "塞尔维亚",
    "巴拉圭": "巴拉圭",
    "民主刚果": "刚果(金)",
    "刚果民主共和国": "刚果(金)",
    "刚果(金)": "刚果(金)",
    "佛得角": "佛得角",
    "美国队": "美国",
    "墨西哥队": "墨西哥",
    "南非队": "南非",
    "科特迪瓦队": "科特迪瓦",
    "刚果金": "刚果(金)",
    "捷克共和国": "捷克",
    "捷克队": "捷克",
}

# When team_a is sporttery away: our label → sporttery hafu key
HAFU_SWAP_FROM_AWAY: dict[str, str] = {
    "胜胜": "aa", "胜平": "ad", "胜负": "ah",
    "平胜": "da", "平平": "dd", "平负": "dh",
    "负胜": "ha", "负平": "hd", "负负": "hh",
}
HAFU_LABELS = list(HAFU_SWAP_FROM_AWAY.keys())

_last_request = 0.0
_cache_pool: list[dict] | None = None
_cache_at: float = 0.0
_last_waf_at: float = 0.0
_last_fetch_error: str | None = None
_last_fetch_ok: bool = False
_last_proxy_used: str | None = None
_CACHE_TTL_SEC = 300
_WAF_BACKOFF_SEC = 120


def get_sporttery_fetch_status() -> dict:
    """Diagnostics for admin / plan API — last fetch outcome and cache state."""
    import time as _time
    from config import SPORTTERY_PROXY

    now = _time.monotonic()
    cache_age = round(now - _cache_at, 1) if _cache_at else None
    return {
        "last_fetch_ok": _last_fetch_ok,
        "last_error": _last_fetch_error,
        "pool_cached": _cache_pool is not None,
        "pool_size": len(_cache_pool) if _cache_pool else 0,
        "cache_age_sec": cache_age,
        "waf_backoff_active": bool(
            _last_waf_at and now - _last_waf_at < _WAF_BACKOFF_SEC
        ),
        "sporttery_proxy_configured": bool(SPORTTERY_PROXY),
        "last_proxy_used": _last_proxy_used,
        "proxy_attempts": [label for label, _ in sporttery_proxy_attempts()],
        "socks_proxy_supported": socks_proxy_supported(),
    }


def normalize_team_name(name: str) -> str:
    if not name:
        return ""
    name = name.strip().replace(" ", "")
    for ch in ("（", "(", "【", "["):
        if ch in name:
            name = name.split(ch, 1)[0]
    for suffix in ("足球队", "国家队", "队"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    if name in SPORTTERY_TEAM_ALIASES:
        return SPORTTERY_TEAM_ALIASES[name]
    if name in CLUB_SPORTTERY_ALIASES:
        return CLUB_SPORTTERY_ALIASES[name]
    return name


def _league_hint_score(league: str, league_hints: tuple[str, ...]) -> int:
    if not league or not league_hints:
        return 0
    for hint in league_hints:
        if hint and hint in league:
            return 20
    return 0


def _parse_float(val) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def _flip_handicap(line: str) -> str:
    line = (line or "").strip()
    if not line:
        return line
    if line.startswith("+"):
        return "-" + line[1:]
    if line.startswith("-"):
        return "+" + line[1:]
    return line


# Official CRS keys from getMatchCalculatorV1 — home_goals:away_goals (sporttery home team).
CRS_SCORE_KEY_MAP: dict[str, tuple[int, int]] = {
    f"s{hg:02d}s{ag:02d}": (hg, ag)
    for hg, ag in (
        (1, 0), (2, 0), (2, 1), (3, 0), (3, 1), (3, 2),
        (4, 0), (4, 1), (4, 2), (5, 0), (5, 1), (5, 2),
        (0, 0), (1, 1), (2, 2), (3, 3),
        (0, 1), (0, 2), (1, 2), (0, 3), (1, 3), (2, 3),
        (0, 4), (1, 4), (2, 4), (0, 5), (1, 5), (2, 5),
    )
}
CRS_OTHER_KEY_LABELS: dict[str, str] = {
    "s1sh": "胜其它",
    "s1sd": "平其它",
    "s1sa": "负其它",
}
CRS_SKIP_KEYS = frozenset({
    "goalLine", "goalLineValue", "updateDate", "updateTime",
    *CRS_OTHER_KEY_LABELS.keys(),
})


def normalize_score_line(score: str) -> str:
    """Normalize score label to team_a:team_b form, e.g. 1：2 → 1:2."""
    if not score:
        return ""
    score = str(score).strip().replace("：", ":").replace("-", ":")
    if ":" not in score:
        return score
    left, right = score.split(":", 1)
    try:
        return f"{int(left.strip())}:{int(right.strip())}"
    except ValueError:
        return score


def _parse_crs_key(key: str) -> Optional[tuple[int, int]]:
    """Parse sporttery crs key like s01s02 → (1, 2) sporttery-home:away goals."""
    if not key or key.endswith("f") or key in CRS_SKIP_KEYS:
        return None
    return CRS_SCORE_KEY_MAP.get(key)


def _score_line_for_team_a(home_g: int, away_g: int, team_a_is_home: bool) -> str:
    if team_a_is_home:
        return f"{home_g}:{away_g}"
    return f"{away_g}:{home_g}"


def _parse_crs_odds(crs: dict, team_a_is_home: bool) -> dict[str, float]:
    """Map sporttery CRS pool to team_a:team_b score odds (official key table)."""
    scores: dict[str, float] = {}
    for key, val in (crs or {}).items():
        if key in CRS_SKIP_KEYS or key.endswith("f"):
            continue
        parsed = _parse_crs_key(key)
        if parsed is None:
            continue
        home_g, away_g = parsed
        odd = _parse_float(val)
        if odd is None:
            continue
        score_key = _score_line_for_team_a(home_g, away_g, team_a_is_home)
        scores[score_key] = odd

    for key, label in CRS_OTHER_KEY_LABELS.items():
        odd = _parse_float((crs or {}).get(key))
        if odd is not None:
            scores[label] = odd
    return scores


def _crs_update_time(crs: dict) -> Optional[datetime]:
    if not crs or not crs.get("updateDate") or not crs.get("updateTime"):
        return None
    try:
        return datetime.strptime(
            f"{crs['updateDate']} {crs['updateTime']}", "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return None


def _parse_hafu_odds(hafu: dict, team_a_is_home: bool) -> dict[str, float]:
    result: dict[str, float] = {}
    if not hafu:
        return result
    if team_a_is_home:
        mapping = {
            "胜胜": "hh", "胜平": "hd", "胜负": "ha",
            "平胜": "dh", "平平": "dd", "平负": "da",
            "负胜": "ah", "负平": "ad", "负负": "aa",
        }
    else:
        mapping = HAFU_SWAP_FROM_AWAY

    for label, st_key in mapping.items():
        odd = _parse_float(hafu.get(st_key))
        if odd is not None:
            result[label] = odd
    return result


def _derive_over_under_from_ttg(ttg: dict) -> tuple[Optional[str], Optional[float], Optional[float]]:
    """Approximate 2.5 goals line from total-goals (TTG) odds."""
    if not ttg:
        return None, None, None
    # s0..s7 = exact 0..6 goals, s7 = 7+
    low = sum(_parse_float(ttg.get(f"s{i}")) or 0 for i in range(3))  # 0-2 goals
    high = sum(_parse_float(ttg.get(f"s{i}")) or 0 for i in range(3, 8))  # 3+ goals
    if low <= 0 and high <= 0:
        return None, None, None
    # Lower implied sum → more likely outcome
    over_odds = round(min(3.5, max(1.5, 2.5 * (low / max(high, 0.01)))), 2)
    under_odds = round(min(3.5, max(1.5, 2.5 * (high / max(low, 0.01)))), 2)
    return "2.5", over_odds, under_odds


def parse_sporttery_sub_match(sub: dict) -> dict:
    """Normalize one subMatchList item from getMatchCalculatorV1."""
    home = normalize_team_name(sub.get("homeTeamAllName") or sub.get("homeTeamAbbName") or "")
    away = normalize_team_name(sub.get("awayTeamAllName") or sub.get("awayTeamAbbName") or "")
    had = sub.get("had") or {}
    hhad = sub.get("hhad") or {}

    match_date = sub.get("matchDate") or ""
    match_time = sub.get("matchTime") or "00:00:00"
    try:
        kickoff = datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        kickoff = None

    return {
        "sporttery_match_id": sub.get("matchId"),
        "match_num": sub.get("matchNumStr") or sub.get("matchNum"),
        "home_team": home,
        "away_team": away,
        "league": sub.get("leagueAllName") or sub.get("leagueAbbName") or "",
        "kickoff": kickoff,
        "had": had,
        "hhad": hhad,
        "crs": sub.get("crs") or {},
        "hafu": sub.get("hafu") or {},
        "ttg": sub.get("ttg") or {},
        "sell_status": sub.get("sellStatus"),
        "raw": sub,
    }


def sporttery_row_has_sale_data(row: dict | None) -> bool:
    """True when sporttery row has on-sale SPF, handicap, or CRS odds."""
    if not row:
        return False
    if row.get("win_win"):
        return True
    if row.get("handicap_win") or row.get("handicap_draw") or row.get("handicap_lose"):
        return True
    return bool(row.get("score_odds"))


def _parse_hhad_odds(hhad: dict, team_a_is_home: bool) -> dict:
    line = (hhad.get("goalLine") or hhad.get("goalLineValue") or "").strip() or None
    if team_a_is_home:
        return {
            "handicap": line,
            "handicap_win": _parse_float(hhad.get("h")),
            "handicap_draw": _parse_float(hhad.get("d")),
            "handicap_lose": _parse_float(hhad.get("a")),
        }
    return {
        "handicap": _flip_handicap(line) or None,
        "handicap_win": _parse_float(hhad.get("a")),
        "handicap_draw": _parse_float(hhad.get("d")),
        "handicap_lose": _parse_float(hhad.get("h")),
    }


def to_db_odds(st_match: dict, team_a: str, team_b: str) -> Optional[dict]:
    """
    Convert sporttery match to our Odds row fields.
    team_a / team_b are from our DB; must match home/away (either order).
    """
    home = st_match["home_team"]
    away = st_match["away_team"]
    our_a = normalize_team_name(team_a)
    our_b = normalize_team_name(team_b)

    if our_a == home and our_b == away:
        team_a_is_home = True
    elif our_a == away and our_b == home:
        team_a_is_home = False
    else:
        return None

    had = st_match.get("had") or {}
    hhad = st_match.get("hhad") or {}
    crs_raw = st_match.get("crs") or {}
    score_odds = _parse_crs_odds(crs_raw, team_a_is_home)
    has_had = bool(had.get("h") or had.get("a"))
    has_hhad = bool(hhad.get("h") or hhad.get("a"))
    has_crs = bool(score_odds)
    if not has_had and not has_hhad and not has_crs:
        return None

    hhad_parsed = _parse_hhad_odds(hhad, team_a_is_home) if has_hhad else {}
    if has_had:
        if team_a_is_home:
            win_win = _parse_float(had.get("h"))
            draw = _parse_float(had.get("d"))
            win_lose = _parse_float(had.get("a"))
        else:
            win_win = _parse_float(had.get("a"))
            draw = _parse_float(had.get("d"))
            win_lose = _parse_float(had.get("h"))
        handicap = hhad_parsed.get("handicap")
        handicap_win = hhad_parsed.get("handicap_win")
        handicap_draw = hhad_parsed.get("handicap_draw")
        handicap_lose = hhad_parsed.get("handicap_lose")
    else:
        win_win = draw = win_lose = None
        handicap = hhad_parsed.get("handicap")
        handicap_win = hhad_parsed.get("handicap_win")
        handicap_draw = hhad_parsed.get("handicap_draw")
        handicap_lose = hhad_parsed.get("handicap_lose")

    over_under, over_odds, under_odds = _derive_over_under_from_ttg(st_match.get("ttg"))
    half_full_odds = _parse_hafu_odds(st_match.get("hafu"), team_a_is_home)

    update_time = None
    if had.get("updateDate") and had.get("updateTime"):
        try:
            update_time = datetime.strptime(
                f"{had['updateDate']} {had['updateTime']}", "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            pass
    crs_time = _crs_update_time(crs_raw)
    if crs_time and (update_time is None or crs_time > update_time):
        update_time = crs_time

    return {
        "win_win": win_win,
        "draw": draw,
        "win_lose": win_lose,
        "handicap": handicap,
        "handicap_win": handicap_win,
        "handicap_draw": handicap_draw,
        "handicap_lose": handicap_lose,
        "over_under": over_under,
        "over_odds": over_odds,
        "under_odds": under_odds,
        "score_odds": score_odds,
        "half_full_odds": half_full_odds,
        "source": "sporttery.cn",
        "sporttery_match_id": st_match.get("sporttery_match_id"),
        "sporttery_match_num": st_match.get("match_num"),
        "update_time": update_time,
    }


async def _rate_limit(min_interval: float = 1.5):
    import asyncio
    import time
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < min_interval:
        await asyncio.sleep(min_interval - elapsed)
    _last_request = time.monotonic()


def _sporttery_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.sporttery.cn/jc/jsq/zqspf/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.sporttery.cn",
    }


def _parse_sporttery_response(data: dict) -> list[dict]:
    results: list[dict] = []
    for day_block in data.get("value", {}).get("matchInfoList") or []:
        sale_date = (
            day_block.get("businessDate")
            or day_block.get("businessdate")
            or day_block.get("matchDate")
            or ""
        )
        for sub in day_block.get("subMatchList") or []:
            parsed = parse_sporttery_sub_match(sub)
            if parsed["home_team"] and parsed["away_team"]:
                parsed["sale_date"] = sale_date or None
                results.append(parsed)
    return results


async def fetch_sporttery_on_sale(*, max_retries: int = 3, force_refresh: bool = False) -> list[dict]:
    """Fetch all on-sale 竞彩足球 matches from sporttery.cn official API."""
    global _cache_pool, _cache_at, _last_waf_at, _last_fetch_error, _last_fetch_ok
    now = time.monotonic()
    if not force_refresh and _cache_pool is not None and now - _cache_at < _CACHE_TTL_SEC:
        return list(_cache_pool)
    if (
        not force_refresh
        and _last_waf_at
        and now - _last_waf_at < _WAF_BACKOFF_SEC
    ):
        if _cache_pool is not None:
            return list(_cache_pool)
        return []

    live = await _fetch_sporttery_live(max_retries=max_retries)
    if live is not None:
        _cache_pool = live
        _cache_at = time.monotonic()
        _last_fetch_ok = True
        _last_fetch_error = None
        return list(live)

    _last_waf_at = time.monotonic()
    _last_fetch_ok = False
    if _cache_pool is not None:
        logger.info("sporttery.cn unavailable — serving cached on-sale matches")
        return list(_cache_pool)
    return []


async def _probe_single_route(label: str, proxy: str | None) -> dict:
    """Test one proxy route without cache."""
    headers = _sporttery_headers()
    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=20,
            follow_redirects=True,
            proxy=proxy,
            trust_env=False,
        ) as client:
            resp = await client.get(
                SPORTTERY_CALCULATOR_API,
                params={"poolCode": "", "channel": "c"},
            )
            ok = resp.status_code == 200
            count = 0
            if ok:
                data = resp.json()
                ok = bool(data.get("success"))
                if ok:
                    count = len(_parse_sporttery_response(data))
            return {
                "route": label,
                "proxy": proxy or "direct",
                "http_status": resp.status_code,
                "ok": ok,
                "pool_size": count,
            }
    except Exception as e:
        err = str(e)
        if "socksio" in err.lower() and proxy and proxy.startswith("socks5"):
            err = "缺少 socksio，请执行 pip install httpx[socks]"
        return {
            "route": label,
            "proxy": proxy or "direct",
            "http_status": None,
            "ok": False,
            "error": err,
        }


async def probe_sporttery_fetch(*, force_refresh: bool = True) -> dict:
    """Admin probe: per-route tests + full fetch."""
    from config import SPORTTERY_PROXY

    route_results = []
    for label, proxy in sporttery_proxy_attempts():
        route_results.append(await _probe_single_route(label, proxy))

    pool = await fetch_sporttery_on_sale(force_refresh=force_refresh)
    status = get_sporttery_fetch_status()
    status["live_pool_size"] = len(pool)
    status["ok"] = _last_fetch_ok
    status["route_results"] = route_results
    status["crawler_proxy_configured"] = bool(get_crawler_proxy())
    from config import SPORTTERY_DIRECT

    status["sporttery_direct_mode"] = SPORTTERY_DIRECT
    status["hint"] = (
        "至少一条 route 的 http_status=200 且 ok=true 才算成功。"
        "国内部署：设置 SPORTTERY_DIRECT=true，体彩直连，Clash 中 sporttery.cn 用 DIRECT。"
        "海外部署：见 deploy/clash-sporttery-rules.yaml。"
    )
    if not socks_proxy_supported():
        status["hint"] += " SOCKS 回退未启用：pip install httpx[socks]（HTTP 代理 7890 仍可用）。"
    return status


async def _fetch_sporttery_live(*, max_retries: int = 3) -> list[dict] | None:
    """Return match list on success (may be empty), None on network/WAF failure."""
    global _last_fetch_error, _last_proxy_used
    await _rate_limit(1.5)
    headers = _sporttery_headers()
    attempts = sporttery_proxy_attempts()
    last_status: int | None = None
    last_error: str | None = None
    saw_567 = False

    for route_label, proxy in attempts:
        for attempt in range(max_retries):
            if attempt > 0:
                await asyncio.sleep(2 ** attempt)
            try:
                async with httpx.AsyncClient(
                    headers=headers,
                    timeout=25,
                    follow_redirects=True,
                    proxy=proxy,
                    trust_env=False,
                ) as client:
                    resp = await client.get(
                        SPORTTERY_CALCULATOR_API,
                        params={"poolCode": "", "channel": "c"},
                    )
                    last_status = resp.status_code
                    if resp.status_code == 567:
                        saw_567 = True
                        if attempt < max_retries - 1:
                            logger.info(
                                f"sporttery.cn HTTP 567 via {route_label}, "
                                f"retry {attempt + 2}/{max_retries}"
                            )
                            continue
                        logger.warning(
                            f"sporttery.cn HTTP 567 via {route_label}"
                            + (f" (proxy={proxy})" if proxy else " (direct)")
                        )
                        break
                    if resp.status_code != 200:
                        _last_fetch_error = f"HTTP {resp.status_code} via {route_label}"
                        logger.warning(f"sporttery.cn {_last_fetch_error}")
                        return None
                    data = resp.json()
                    if not data.get("success"):
                        _last_fetch_error = data.get("errorMessage") or "API success=false"
                        logger.warning(f"sporttery.cn API error: {_last_fetch_error}")
                        return None

                    results = _parse_sporttery_response(data)
                    _last_proxy_used = route_label
                    logger.info(
                        f"sporttery.cn: fetched {len(results)} on-sale matches "
                        f"via {route_label}"
                        + (f" (proxy={proxy})" if proxy else " (direct)")
                    )
                    return results
            except Exception as e:
                last_error = str(e) or type(e).__name__
                if "socksio" in last_error.lower() and proxy and str(proxy).startswith("socks5"):
                    logger.warning(
                        f"sporttery.cn skip {route_label}: socksio not installed "
                        "(pip install httpx[socks])"
                    )
                    break
                if attempt < max_retries - 1:
                    logger.info(
                        f"sporttery.cn fetch error via {route_label}, "
                        f"retry {attempt + 2}/{max_retries}: {last_error}"
                    )
                    continue
                logger.warning(f"sporttery.cn fetch failed via {route_label}: {last_error}")

        if last_status == 567:
            continue

    if saw_567 and SPORTTERY_PLAYWRIGHT_FALLBACK:
        for label, proxy in attempts:
            pw = await _fetch_sporttery_via_playwright(proxy)
            if pw is not None:
                _last_proxy_used = f"playwright:{label}"
                return pw

    if saw_567:
        _last_fetch_error = WAF_BLOCKED_HINT
        logger.warning(WAF_BLOCKED_HINT)
    elif last_error:
        _last_fetch_error = last_error
        logger.warning(f"sporttery.cn fetch failed: {last_error}")
    else:
        _last_fetch_error = f"HTTP {last_status}"
        logger.warning(f"sporttery.cn fetch failed: HTTP {last_status}")
    return None


def _playwright_proxy_dict(proxy: str | None) -> dict | None:
    if not proxy:
        return None
    parsed = urlparse(proxy)
    if not parsed.hostname:
        return None
    out: dict = {"server": proxy}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


async def _fetch_sporttery_via_playwright(proxy: str | None) -> list[dict] | None:
    """Browser fallback — real TLS/cookies; uses same proxy as httpx attempts."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("playwright not installed — skip sporttery browser fallback")
        return None

    api_url = f"{SPORTTERY_CALCULATOR_API}?poolCode=&channel=c"
    headers = _sporttery_headers()
    proxy_cfg = _playwright_proxy_dict(proxy)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx_opts: dict = {
                    "user_agent": headers["User-Agent"],
                    "locale": "zh-CN",
                    "extra_http_headers": {
                        "Accept-Language": headers["Accept-Language"],
                        "Referer": headers["Referer"],
                    },
                }
                if proxy_cfg:
                    ctx_opts["proxy"] = proxy_cfg
                context = await browser.new_context(**ctx_opts)
                page = await context.new_page()
                await page.goto(
                    "https://www.sporttery.cn/jc/jsq/zqspf/",
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                resp = await page.goto(api_url, wait_until="commit", timeout=45000)
                if not resp or resp.status != 200:
                    logger.warning(
                        f"sporttery playwright HTTP {resp.status if resp else 'none'}"
                        + (f" proxy={proxy}" if proxy else "")
                    )
                    return None
                data = json.loads(await resp.text())
                if not data.get("success"):
                    return None
                results = _parse_sporttery_response(data)
                logger.info(
                    f"sporttery.cn: playwright fetched {len(results)} matches"
                    + (f" via {proxy}" if proxy else " direct")
                )
                return results
            finally:
                await browser.close()
    except Exception as e:
        logger.warning(f"sporttery playwright fallback failed: {e}")
        return None


def find_sporttery_match_by_id(
    sporttery_match_id: int | str | None,
    sporttery_matches: list[dict],
) -> Optional[dict]:
    """Direct lookup by sporttery matchId — most reliable when stored."""
    if sporttery_match_id is None:
        return None
    target = str(sporttery_match_id)
    for st in sporttery_matches:
        if str(st.get("sporttery_match_id")) == target:
            return st
    return None


def find_sporttery_match(
    team_a: str,
    team_b: str,
    match_time: Optional[datetime],
    sporttery_matches: list[dict],
    *,
    league_hint: str = "世界",
    league_hints: tuple[str, ...] | None = None,
    sporttery_match_id: int | str | None = None,
) -> Optional[dict]:
    """
    Match a DB fixture to sporttery on-sale data by team names + kickoff time.
    Prefers entries whose league name matches competition hints when provided.
    """
    by_id = find_sporttery_match_by_id(sporttery_match_id, sporttery_matches)
    if by_id:
        home, away = by_id["home_team"], by_id["away_team"]
        our_a, our_b = normalize_team_name(team_a), normalize_team_name(team_b)
        if (our_a == home and our_b == away) or (our_a == away and our_b == home):
            return by_id

    hints = league_hints or ((league_hint,) if league_hint else ())
    our_a = normalize_team_name(team_a)
    our_b = normalize_team_name(team_b)
    candidates: list[tuple[int, dict]] = []

    for st in sporttery_matches:
        home, away = st["home_team"], st["away_team"]
        home_n, away_n = normalize_team_name(home), normalize_team_name(away)
        teams_ok = (our_a == home_n and our_b == away_n) or (our_a == away_n and our_b == home_n)
        if not teams_ok:
            continue

        score = 10
        if match_time and st.get("kickoff"):
            delta_h = abs((match_time - st["kickoff"]).total_seconds()) / 3600
            if delta_h <= 2:
                score += 10
            elif delta_h <= 24:
                score += 5
            elif delta_h <= 72:
                score += 2

        league = st.get("league") or ""
        score += _league_hint_score(league, hints)

        candidates.append((score, st))

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][1]
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best = candidates[0]
    # When hints provided, reject cross-league false positives with weak scores
    if hints and best_score < 20 and len(candidates) > 1:
        hinted = [c for c in candidates if c[0] >= 20]
        if hinted:
            hinted.sort(key=lambda x: x[0], reverse=True)
            return hinted[0][1]
    # Strong team + kickoff alignment is enough even when league label differs
    if hints and best_score < 5:
        if match_time and best.get("kickoff"):
            delta_h = abs((match_time - best["kickoff"]).total_seconds()) / 3600
            if delta_h <= 48:
                return best
        return None
    return best


# Backward-compatible alias
async def fetch_sporttery_odds(match_date: str = None) -> list[dict]:
    """Legacy entry — returns all on-sale matches (date filter applied client-side)."""
    matches = await fetch_sporttery_on_sale()
    if not match_date:
        return matches
    return [
        m for m in matches
        if m.get("kickoff") and m["kickoff"].strftime("%Y-%m-%d") == match_date
    ]
