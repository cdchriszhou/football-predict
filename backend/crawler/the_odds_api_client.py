"""
The Odds API client — real European + Asian handicap markets for FIFA World Cup.

Docs: https://the-odds-api.com/liveapi/guides/v4/
Requires ODDS_API_KEY in environment (.env).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from statistics import mean
from typing import Optional

import httpx

from crawler.team_crawler import TEAM_NAME_MAP, EN_TO_CN_TEAM, WIKIPEDIA_NAME_ALIASES
from utils.logger import logger
from utils.http_client import get_crawler_proxy

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "soccer_fifa_world_cup"

# Prefer sharp EU books for 1X2; AU/EU for Asian handicap
EU_H2H_BOOKS = {"pinnacle", "betfair_ex_eu", "williamhill", "unibet_eu", "bet365"}
ASIAN_BOOKS = {"pinnacle", "betfair_ex_eu", "bet365", "sportsbet", "tab"}

_last_request = 0.0

# The Odds API may use short or variant English names
ODDS_API_TEAM_ALIASES = {
    "USA": "United States",
    "U.S.A.": "United States",
    "Korea Republic": "South Korea",
    "Republic of Korea": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "DR Congo": "DR Congo",
    "Congo DR": "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Cabo Verde": "Cape Verde",
    "Saudi": "Saudi Arabia",
    "Kingdom of Saudi Arabia": "Saudi Arabia",
}


def _normalize_api_team(name: str) -> str:
    n = (name or "").strip()
    n = n.replace(" & ", " and ")
    return ODDS_API_TEAM_ALIASES.get(n, n)


def cn_to_en(team_cn: str) -> str:
    return TEAM_NAME_MAP.get(team_cn, team_cn)


def en_to_cn(team_en: str) -> str:
    team_en = _normalize_api_team(team_en)
    if team_en in EN_TO_CN_TEAM:
        return EN_TO_CN_TEAM[team_en]
    alias = WIKIPEDIA_NAME_ALIASES.get(team_en)
    if alias and alias in EN_TO_CN_TEAM:
        return EN_TO_CN_TEAM[alias]
    try:
        from data.club_name_map import resolve_club_cn
        cn = resolve_club_cn(name_en=team_en)
        if cn and cn != team_en:
            return cn
    except Exception:
        pass
    return team_en


def _normalize_en(name: str) -> str:
    n = (name or "").strip().lower().replace("'", "'")
    n = n.replace(" & ", " and ")
    return n


def _teams_match(our_a: str, our_b: str, api_home: str, api_away: str) -> tuple[bool, bool]:
    """
    Match DB teams to API home/away.
    Returns (matched, team_a_is_home).
    """
    our_a_en = _normalize_en(cn_to_en(our_a))
    our_b_en = _normalize_en(cn_to_en(our_b))
    home_en = _normalize_en(_normalize_api_team(api_home))
    away_en = _normalize_en(_normalize_api_team(api_away))

    if our_a_en == home_en and our_b_en == away_en:
        return True, True
    if our_a_en == away_en and our_b_en == home_en:
        return True, False
    return False, True


def _avg_prices(outcomes: list[dict], name: str) -> Optional[float]:
    prices = [o["price"] for o in outcomes if o.get("name") == name and o.get("price")]
    return round(mean(prices), 2) if prices else None


def _parse_h2h_markets(bookmakers: list[dict], home: str, away: str) -> dict:
    home_prices, draw_prices, away_prices = [], [], []
    used_books = []

    def _collect(allowed_books: set[str] | None):
        home_prices.clear()
        draw_prices.clear()
        away_prices.clear()
        used_books.clear()
        for bk in bookmakers:
            if allowed_books and bk.get("key") not in allowed_books:
                continue
            for m in bk.get("markets") or []:
                if m.get("key") != "h2h":
                    continue
                outcomes = m.get("outcomes") or []
                h = _avg_prices(outcomes, home)
                d = _avg_prices(outcomes, "Draw")
                a = _avg_prices(outcomes, away)
                if h and d and a:
                    home_prices.append(h)
                    draw_prices.append(d)
                    away_prices.append(a)
                    used_books.append(bk.get("key"))

    _collect(EU_H2H_BOOKS)
    if not home_prices:
        _collect(None)
    if not home_prices:
        return {}
    return {
        "home_win": round(mean(home_prices), 2),
        "draw": round(mean(draw_prices), 2),
        "away_win": round(mean(away_prices), 2),
        "bookmakers": used_books,
    }


def _collect_spreads(bookmakers: list[dict], home: str, away: str, allowed_books: set[str] | None) -> dict:
    lines: dict[float, list] = {}
    used_books = []
    for bk in bookmakers:
        if allowed_books and bk.get("key") not in allowed_books:
            continue
        has_spreads = False
        for m in bk.get("markets") or []:
            if m.get("key") != "spreads":
                continue
            has_spreads = True
            for o in m.get("outcomes") or []:
                point = o.get("point")
                price = o.get("price")
                name = o.get("name")
                if point is None or not price or not name:
                    continue
                key = float(point)
                if key not in lines:
                    lines[key] = {"home": [], "away": []}
                if name == home:
                    lines[key]["home"].append(price)
                elif name == away:
                    lines[key]["away"].append(price)
        if has_spreads and bk.get("key"):
            used_books.append(bk.get("key"))
    return {"lines": lines, "used_books": used_books}


def _parse_spreads(bookmakers: list[dict], home: str, away: str) -> dict:
    """Asian handicap from spreads market (real bookmaker lines)."""
    bucket = _collect_spreads(bookmakers, home, away, ASIAN_BOOKS)
    lines = bucket["lines"]
    used_books = bucket["used_books"]
    if not lines:
        bucket = _collect_spreads(bookmakers, home, away, None)
        lines = bucket["lines"]
        used_books = bucket["used_books"]
    if not lines:
        return {}
    # Pick line with most bookmaker coverage
    best_line = max(lines.keys(), key=lambda k: len(lines[k]["home"]) + len(lines[k]["away"]))
    bucket = lines[best_line]
    if not bucket["home"] or not bucket["away"]:
        return {}
    h = round(mean(bucket["home"]), 2)
    a = round(mean(bucket["away"]), 2)
    line_str = f"{best_line:+.1f}".replace(".0", "")
    return {
        "handicap": line_str,
        "handicap_home": h,
        "handicap_away": a,
        "bookmakers": list(set(used_books)),
    }


def _parse_totals(bookmakers: list[dict]) -> dict:
    totals: dict[float, list] = {}
    for bk in bookmakers:
        for m in bk.get("markets") or []:
            if m.get("key") != "totals":
                continue
            for o in m.get("outcomes") or []:
                point = o.get("point")
                price = o.get("price")
                label = (o.get("name") or "").lower()
                if point is None or not price:
                    continue
                key = float(point)
                if key not in totals:
                    totals[key] = {"over": [], "under": []}
                if "over" in label:
                    totals[key]["over"].append(price)
                elif "under" in label:
                    totals[key]["under"].append(price)
    if not totals:
        return {}
    best = max(totals.keys(), key=lambda k: len(totals[k]["over"]) + len(totals[k]["under"]))
    b = totals[best]
    if not b["over"] or not b["under"]:
        return {}
    line = str(int(best)) if best == int(best) else str(best)
    return {
        "over_under": line,
        "over_odds": round(mean(b["over"]), 2),
        "under_odds": round(mean(b["under"]), 2),
    }


def _to_team_a_perspective(h2h: dict, spreads: dict, totals: dict, team_a_is_home: bool) -> dict:
    if not h2h:
        return {}
    win_a = h2h["home_win"] if team_a_is_home else h2h["away_win"]
    win_b = h2h["away_win"] if team_a_is_home else h2h["home_win"]
    european = {
        "win_win": win_a,
        "draw": h2h["draw"],
        "win_lose": win_b,
        "source": "the-odds-api",
        "bookmakers": h2h.get("bookmakers", []),
    }
    if totals:
        european.update(totals)

    macau = {}
    if spreads:
        line = spreads["handicap"]
        if not team_a_is_home:
            # flip sign for team_a perspective
            try:
                v = float(str(line).replace("+", ""))
                if str(line).startswith("-"):
                    line = f"+{v:g}"
                elif str(line).startswith("+"):
                    line = f"-{v:g}"
                else:
                    line = f"-{v:g}" if v > 0 else f"+{abs(v):g}"
            except ValueError:
                pass
        macau = {
            "win_win": win_a,
            "draw": h2h["draw"],
            "win_lose": win_b,
            "handicap": line,
            "handicap_win": spreads["handicap_home"] if team_a_is_home else spreads["handicap_away"],
            "handicap_lose": spreads["handicap_away"] if team_a_is_home else spreads["handicap_home"],
            "handicap_draw": round((win_a + win_b) / 2 + 0.8, 2),
            "source": "the-odds-api:asian_handicap",
            "bookmakers": spreads.get("bookmakers", []),
        }
        if totals:
            macau.update({k: totals[k] for k in ("over_under", "over_odds", "under_odds") if k in totals})

    return {"european": european, "macau": macau}


async def fetch_sport_odds(sport_key: str, label: str = "") -> list[dict]:
    """Fetch upcoming fixtures with real bookmaker odds for any sport key."""
    api_key = os.getenv("ODDS_API_KEY", "")
    if not api_key:
        logger.warning("ODDS_API_KEY not set — skip The Odds API")
        return []

    import asyncio
    import time
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < 1.0:
        await asyncio.sleep(1.0 - elapsed)
    _last_request = time.monotonic()

    params = {
        "apiKey": api_key,
        "regions": "eu,uk,au",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "decimal",
    }
    proxy = get_crawler_proxy()
    try:
        async with httpx.AsyncClient(timeout=30, proxy=proxy, follow_redirects=True) as client:
            resp = await client.get(f"{ODDS_API_BASE}/sports/{sport_key}/odds", params=params)
            if resp.status_code != 200:
                logger.warning(f"The Odds API HTTP {resp.status_code} [{sport_key}]: {resp.text[:200]}")
                return []
            events = resp.json()
    except Exception as e:
        logger.warning(f"The Odds API fetch failed [{sport_key}]: {e}")
        return []

    parsed = []
    for ev in events:
        home = ev.get("home_team")
        away = ev.get("away_team")
        if not home or not away:
            continue
        commence = ev.get("commence_time")
        kickoff = None
        if commence:
            try:
                kickoff = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            except ValueError:
                pass
        bookmakers = ev.get("bookmakers") or []
        h2h = _parse_h2h_markets(bookmakers, home, away)
        spreads = _parse_spreads(bookmakers, home, away)
        totals = _parse_totals(bookmakers)
        if not h2h:
            continue
        parsed.append({
            "event_id": ev.get("id"),
            "home_team_en": home,
            "away_team_en": away,
            "home_team_cn": en_to_cn(home),
            "away_team_cn": en_to_cn(away),
            "kickoff": kickoff,
            "h2h": h2h,
            "spreads": spreads,
            "totals": totals,
            "raw_bookmaker_count": len(bookmakers),
        })
    tag = label or sport_key
    logger.info(f"The Odds API [{tag}]: {len(parsed)} events with real odds")
    return parsed


async def fetch_world_cup_odds() -> list[dict]:
    """Fetch all upcoming World Cup fixtures with real bookmaker odds."""
    return await fetch_sport_odds(SPORT_KEY, "World Cup")


def find_odds_api_match(
    team_a: str,
    team_b: str,
    match_time: Optional[datetime],
    pool: list[dict],
) -> Optional[dict]:
    """Match a DB fixture to The Odds API event; return european+macau dict."""
    candidates = []
    for ev in pool:
        ok, a_is_home = _teams_match(team_a, team_b, ev["home_team_en"], ev["away_team_en"])
        if not ok:
            continue
        score = 0
        if match_time and ev.get("kickoff"):
            kt = ev["kickoff"]
            if kt.tzinfo is None:
                kt = kt.replace(tzinfo=timezone.utc)
            mt = match_time
            if mt.tzinfo is None:
                mt = mt.replace(tzinfo=timezone.utc)
            delta_h = abs((mt - kt).total_seconds()) / 3600
            if delta_h <= 3:
                score += 10
            elif delta_h <= 24:
                score += 5
            elif delta_h <= 72:
                score += 2
        candidates.append((score, ev, a_is_home))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, ev, a_is_home = candidates[0]
    return _to_team_a_perspective(ev["h2h"], ev.get("spreads") or {}, ev.get("totals") or {}, a_is_home)
