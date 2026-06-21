"""Hong Kong Jockey Club public GraphQL + results page client."""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from crawler.hkjc_queries import RACE_MEETINGS_QUERY, RACE_ODDS_QUERY
from utils.logger import logger

HKJC_GRAPHQL_URL = "https://info.cld.hkjc.com/graphql/base/"
HKJC_RACING_BASE = "https://racing.hkjc.com/racing/information/Chinese/Racing"
HKJC_LOCAL_INFO = "https://racing.hkjc.com/zh-hk/local/information"
HK_TZ = ZoneInfo("Asia/Hong_Kong")

VENUE_LABELS = {
    "ST": ("沙田", "Sha Tin"),
    "HV": ("跑马地", "Happy Valley"),
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh-TW;q=0.9,zh-CN;q=0.8,en;q=0.7",
    "Referer": "https://bet.hkjc.com/",
    "Origin": "https://bet.hkjc.com",
    "Content-Type": "application/json",
}


class HkjcClientError(Exception):
    pass


class HkjcClient:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def _post_graphql(
        self,
        operation_name: str,
        query: str,
        variables: dict | None = None,
    ) -> dict:
        payload = {
            "operationName": operation_name,
            "variables": variables or {},
            "query": query,
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.post(HKJC_GRAPHQL_URL, json=payload, headers=DEFAULT_HEADERS)
        if resp.status_code != 200:
            raise HkjcClientError(f"GraphQL HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("errors"):
            raise HkjcClientError(str(body["errors"]))
        return body.get("data") or {}

    async def fetch_active_meetings(self) -> list[dict]:
        data = await self._post_graphql("raceMeetings", RACE_MEETINGS_QUERY, {})
        return data.get("activeMeetings") or []

    async def fetch_meeting(self, meeting_date: str, venue_code: str) -> dict | None:
        data = await self._post_graphql(
            "raceMeetings",
            RACE_MEETINGS_QUERY,
            {"date": meeting_date, "venueCode": venue_code},
        )
        meetings = data.get("raceMeetings") or []
        return meetings[0] if meetings else None

    async def fetch_win_odds(
        self, meeting_date: str, venue_code: str, race_no: int
    ) -> dict[int, float]:
        data = await self._post_graphql(
            "racing",
            RACE_ODDS_QUERY,
            {
                "date": meeting_date,
                "venueCode": venue_code,
                "oddsTypes": ["WIN"],
                "raceNo": race_no,
            },
        )
        odds_map: dict[int, float] = {}
        meetings = data.get("raceMeetings") or []
        if not meetings:
            return odds_map
        for pool in meetings[0].get("pmPools") or []:
            if pool.get("oddsType") != "WIN":
                continue
            for node in pool.get("oddsNodes") or []:
                comb = str(node.get("combString") or "").strip()
                if not comb.isdigit():
                    continue
                try:
                    odds_map[int(comb)] = float(node.get("oddsValue") or 0)
                except (TypeError, ValueError):
                    continue
        return odds_map

    async def fetch_html(self, url: str) -> str:
        headers = {**DEFAULT_HEADERS}
        headers.pop("Content-Type", None)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HkjcClientError(f"HTTP {resp.status_code} for {url}")
        return resp.text

    async def fetch_race_result(
        self, race_date: date, venue_code: str, race_no: int
    ) -> dict | None:
        """Parse official LocalResults page for one race."""
        date_str = race_date.strftime("%Y/%m/%d")
        course = venue_code.upper()
        url = (
            f"{HKJC_RACING_BASE}/LocalResults.aspx"
            f"?RaceDate={date_str}&Racecourse={course}&RaceNo={race_no}"
        )
        try:
            html = await self.fetch_html(url)
        except HkjcClientError as e:
            logger.warning(f"HKJC result fetch failed {url}: {e}")
            return None
        return _parse_local_results(html, race_date, course, race_no)


def _parse_local_results(html: str, race_date: date, venue_code: str, race_no: int) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table")
    if not tables:
        return None

    meta_text = soup.get_text("\n", strip=True)
    distance_m = _extract_int(r"(\d{3,4})米", meta_text)
    race_class = _extract_group(r"第([一二三四五六七八九十\d]+班)", meta_text) or ""
    going = _extract_group(r"(好地|好地至快地|快地|黏地|软地|大爛地|濕慢地)[^\n]*", meta_text) or ""
    track_type = "草地" if "草地" in meta_text or "Turf" in meta_text else (
        "泥地" if "泥" in meta_text or "All Weather" in meta_text else "草地"
    )

    finishers: list[dict] = []
    for table in tables:
        rows = table.select("tr")
        if len(rows) < 2:
            continue
        header = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not header or "名次" not in header[0] and "Pla" not in header[0]:
            continue
        idx = {name: i for i, name in enumerate(header)}
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 5:
                continue
            placing_raw = cells[idx.get("名次", idx.get("Pla", 0))]
            if not placing_raw or placing_raw in ("-", "WV", "WX"):
                continue
            try:
                placing = int(re.sub(r"\D", "", placing_raw) or "0")
            except ValueError:
                continue
            horse_no = _safe_int(cells[idx.get("馬號", idx.get("No.", 1))])
            name = cells[idx.get("馬名", idx.get("Horse", 2))]
            jockey = cells[idx.get("騎師", idx.get("Jockey", 3))]
            trainer = cells[idx.get("練馬師", idx.get("Trainer", 4))]
            draw = _safe_int(cells[idx.get("檔位", idx.get("Draw", 7 if len(cells) > 7 else 6))])
            odds = _safe_float(cells[idx.get("獨贏賠率", idx.get("Win Odds", -1))] if len(cells) > 8 else None)
            finishers.append({
                "placing": placing,
                "horse_no": horse_no,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "draw": draw,
                "odds": odds,
            })
        if finishers:
            break

    if not finishers:
        return None

    return {
        "race_date": race_date.isoformat(),
        "meeting_date": race_date.isoformat(),
        "venue_code": venue_code,
        "race_no": race_no,
        "distance_m": distance_m or 0,
        "class": race_class,
        "track_type": track_type,
        "going": going,
        "finishers": finishers,
        "winner_horse_no": next((f["horse_no"] for f in finishers if f["placing"] == 1), None),
    }


def _extract_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_group(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _safe_int(val) -> int:
    if val is None:
        return 0
    try:
        return int(re.sub(r"\D", "", str(val)) or "0")
    except ValueError:
        return 0


def _safe_float(val) -> float | None:
    if val is None or val == "" or val == "-":
        return None
    try:
        return float(str(val).replace(",", ""))
    except ValueError:
        return None


def meeting_id_from(date_str: str, venue_code: str) -> str:
    d = date_str.replace("/", "-")[:10]
    return f"{d.replace('-', '')}-{venue_code.lower()}"


def normalize_meeting_date(raw: str) -> str:
    """GraphQL date -> YYYY-MM-DD."""
    if not raw:
        return ""
    raw = raw.strip()
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    return raw.replace("/", "-")


def distance_category(distance_m: int) -> str:
    if distance_m <= 1200:
        return "短途"
    if distance_m <= 1600:
        return "中距"
    return "长途"


def parse_last6run(form: str) -> list[int]:
    """Parse HKJC last6run like '1/2/3/4/5/6' or '1/2/3'."""
    if not form:
        return []
    parts = re.split(r"[/\s\-]+", form.strip())
    out: list[int] = []
    for p in parts:
        p = p.strip()
        if not p or p in ("-", "X"):
            continue
        try:
            out.append(int(re.sub(r"\D", "", p)))
        except ValueError:
            continue
    return out


def compute_runner_stats(last6: list[int], distance_m: int, draw: int) -> dict:
    """Derive model features from real recent form."""
    n = len(last6) or 1
    wins = sum(1 for x in last6 if x == 1)
    places = sum(1 for x in last6 if x <= 3)
    win_rate = wins / n
    place_rate = places / n
    avg_pos = sum(last6) / n if last6 else 6.0
    form_score = max(0.0, min(1.0, 1.0 - (avg_pos - 1) / 8))
    draw_fit = 0.92 if draw == 1 else 0.85 if draw <= 3 else 0.78 if draw <= 6 else 0.68 if draw <= 9 else 0.62
    dist_fit = 0.85
    if distance_m <= 1200:
        dist_fit = 0.90 if avg_pos <= 4 else 0.75
    elif distance_m >= 1800:
        dist_fit = 0.88 if avg_pos <= 5 else 0.72
    return {
        "win_rate_10": round(win_rate, 3),
        "place_rate_10": round(place_rate, 3),
        "distance_fit": round(dist_fit, 3),
        "track_fit": 0.85,
        "draw_fit": round(draw_fit, 3),
        "jockey_pair_rate": 0.15,
        "trainer_rate": 0.15,
        "form_score": round(form_score, 3),
    }


def map_graphql_meeting(raw: dict, odds_by_race: dict[int, dict[int, float]] | None = None) -> dict:
    """Convert GraphQL meeting to internal schema."""
    date_str = normalize_meeting_date(raw.get("date") or "")
    venue_code = (raw.get("venueCode") or "").upper()
    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    meeting_id = meeting_id_from(date_str, venue_code)
    races_out: list[dict] = []
    horses_seen: dict[str, dict] = {}

    for race in raw.get("races") or []:
        race_no = int(race.get("no") or 0)
        distance_m = int(race.get("distance") or 0)
        dist_cat = distance_category(distance_m)
        race_id = f"{meeting_id}-r{race_no}"
        track_desc = (race.get("raceTrack") or {}).get("description_ch") or ""
        track_type = "泥地" if "泥" in track_desc or "AW" in track_desc else "草地"
        going = race.get("go_ch") or race.get("go_en") or ""
        post_time = race.get("postTime") or ""
        race_odds = (odds_by_race or {}).get(race_no) or {}

        runners_out: list[dict] = []
        for r in race.get("runners") or []:
            if (r.get("status") or "").upper() in ("SCR", "SCRATCHED", "WITHDRAWN"):
                continue
            horse_no = int(r.get("no") or 0)
            last6 = parse_last6run(r.get("last6run") or "")
            draw = int(r.get("barrierDrawNumber") or 0)
            stats = compute_runner_stats(last6, distance_m, draw)
            odds = race_odds.get(horse_no)
            if odds is None:
                try:
                    odds = float(r.get("winOdds") or 0) or None
                except (TypeError, ValueError):
                    odds = None
            weight_delta = 0.0
            try:
                cw = float(r.get("currentWeight") or 0)
                hw = float(r.get("handicapWeight") or 0)
                if cw and hw:
                    weight_delta = round(cw - hw, 1)
            except (TypeError, ValueError):
                pass
            name = r.get("name_ch") or r.get("name_en") or ""
            jockey = (r.get("jockey") or {}).get("name_ch") or (r.get("jockey") or {}).get("name_en") or ""
            trainer = (r.get("trainer") or {}).get("name_ch") or (r.get("trainer") or {}).get("name_en") or ""
            horse_code = (r.get("horse") or {}).get("code") or ""
            recent_form = "/".join(str(x) for x in last6) if last6 else (r.get("last6run") or "")

            runner = {
                "horse_no": horse_no,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "draw": draw,
                "weight": float(r.get("handicapWeight") or 0),
                "weight_delta": weight_delta,
                "rating": int(r.get("currentRating") or 0),
                "age": 0,
                "sex": "",
                "recent_form": recent_form,
                "stats": stats,
                "odds": odds or 99.0,
                "tags": [],
                "horse_code": horse_code,
            }
            if odds and odds <= 5:
                runner["tags"].append("热门")
            runners_out.append(runner)
            if horse_code and horse_code not in horses_seen:
                horses_seen[horse_code] = {
                    "name": name,
                    "rating": runner["rating"],
                    "age": 0,
                    "sex": "",
                    "trainer": trainer,
                    "recent_form": recent_form,
                    "horse_code": horse_code,
                }

        risk = "medium"
        if len(runners_out) >= 12 or dist_cat == "长途":
            risk = "high"
        elif len(runners_out) <= 8 and dist_cat == "短途":
            risk = "low"

        races_out.append({
            "id": race_id,
            "meeting_id": meeting_id,
            "race_no": race_no,
            "name": race.get("raceName_ch") or race.get("raceName_en") or f"第{race_no}场",
            "distance_m": distance_m,
            "distance_category": dist_cat,
            "class": race.get("raceClass_ch") or race.get("raceClass_en") or "",
            "track_type": track_type,
            "start_time": post_time,
            "prize_hkd": 0,
            "risk_level": risk,
            "going": going,
            "runners": runners_out,
        })

    races_out.sort(key=lambda x: x["race_no"])
    return {
        "id": meeting_id,
        "date": date_str,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "track_type": races_out[0]["track_type"] if races_out else "草地",
        "track_rating": races_out[0].get("going", "") if races_out else "",
        "weather": "",
        "temperature_c": None,
        "race_count": len(races_out),
        "meeting_risk": "medium",
        "featured": (raw.get("status") or "").upper() in ("ACTIVE", "CURRENT", "OPEN"),
        "status": raw.get("status") or "",
        "races": races_out,
        "horses_index": sorted(horses_seen.values(), key=lambda h: -h.get("rating", 0)),
    }


async def discover_recent_result_dates(client: HkjcClient, days: int = 60) -> list[tuple[date, str]]:
    """Walk back calendar days and probe ST/HV for existing results."""
    found: list[tuple[date, str]] = []
    today = datetime.now(HK_TZ).date()
    for i in range(days):
        d = today - timedelta(days=i)
        for venue in ("ST", "HV"):
            res = await client.fetch_race_result(d, venue, 1)
            if res and res.get("finishers"):
                found.append((d, venue))
                break
        await asyncio.sleep(0.15)
    return found
