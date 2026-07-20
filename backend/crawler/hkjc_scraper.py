"""Scrape official HKJC racing.hkjc.com HTML pages (RaceCard / LocalResults / ResultsAll)."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from bs4 import BeautifulSoup

from crawler.hkjc_client import (
    HKJC_LOCAL_INFO,
    HKJC_RACING_BASE,
    HkjcClient,
    compute_runner_stats,
    distance_category,
    map_graphql_meeting,
    meeting_id_from,
    parse_last6run,
)

VENUE_LABELS = {
    "ST": ("沙田", "Sha Tin"),
    "HV": ("跑马地", "Happy Valley"),
}

RUNNER_HEADER_KEYS = ("6次近績", "6次近绩", "馬匹編號", "马匹编号")


def _parse_weight_delta(raw: str) -> float:
    if not raw or raw in ("-", "—"):
        return 0.0
    raw = raw.replace("+", "+").strip()
    try:
        return float(raw)
    except ValueError:
        m = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
        return float(m.group(0)) if m else 0.0


def _safe_int(val) -> int:
    try:
        return int(re.sub(r"\D", "", str(val)) or "0")
    except ValueError:
        return 0


def _find_header_col(header: list[str], *needles: str) -> int | None:
    for i, h in enumerate(header):
        for n in needles:
            if n in h:
                return i
    return None


def _find_rating_col(header: list[str]) -> int | None:
    """Avoid matching 評分+/- or 國際評分 when looking for current handicap rating."""
    exact = ("評分", "评分", "Rtg.", "現時評分", "现时评分", "Rating")
    for i, h in enumerate(header):
        if any(x in h for x in ("+/-", "國際", "国际", "Int'l", "国际评分")):
            continue
        if h.strip() in exact:
            return i
    for i, h in enumerate(header):
        if any(x in h for x in ("+/-", "國際", "国际", "Int'l")):
            continue
        if "評分" in h or "评分" in h or "Rtg" in h:
            return i
    return _find_header_col(header, "國際評分", "国际评分", "Int'l Rtg.")


def _cell_at(cells: list[str], idx: int | None, default: str = "") -> str:
    if idx is None or idx < 0 or idx >= len(cells):
        return default
    return cells[idx]


def _racecard_fetch_urls(meeting_date: str, venue_code: str, race_no: int) -> list[str]:
    """Official racecard URLs (zh-hk first; avoid Racecourse= on zh-hk — breaks table)."""
    date_slash = meeting_date.replace("-", "/")
    vc = venue_code.upper()
    return [
        f"{HKJC_LOCAL_INFO}/racecard?racedate={date_slash}&RaceNo={race_no}",
        f"{HKJC_LOCAL_INFO}/racecard?RaceNo={race_no}",
        f"{HKJC_LOCAL_INFO}/racecard",
        f"{HKJC_RACING_BASE}/RaceCard.aspx?RaceDate={date_slash}&RaceNo={race_no}",
        f"{HKJC_RACING_BASE}/RaceCard.aspx?RaceDate={date_slash}&Racecourse={vc}&RaceNo={race_no}",
    ]


async def fetch_parsed_racecard(
    client: HkjcClient,
    meeting_date: str,
    venue_code: str,
    race_no: int,
) -> dict | None:
    """Fetch racecard HTML and parse runners; tries zh-hk and legacy paths."""
    expected_id = meeting_id_from(meeting_date, venue_code.upper())
    for url in _racecard_fetch_urls(meeting_date, venue_code, race_no):
        try:
            html = await client.fetch_html(url)
        except Exception:
            continue
        race = parse_racecard_html(html, meeting_date, venue_code.upper(), race_no)
        if not race or not race.get("runners"):
            continue
        if race.get("meeting_id") and race["meeting_id"] != expected_id:
            continue
        return race
    return None


def _parse_horse_sex(raw: str) -> str:
    if not raw or raw in ("-", "—"):
        return ""
    text = raw.strip()
    for token in ("雌", "牝", "雄", "閹", "騸", "G", "M", "F", "C", "H"):
        if token in text:
            if token in ("G", "M"):
                return "雄" if token == "G" else "雌"
            if token in ("F", "C", "H"):
                return {"F": "雌", "C": "閹", "H": "雄"}.get(token, token)
            return token
    return text[:4] if len(text) <= 4 else ""


def _parse_horse_age(raw: str) -> int:
    if not raw or raw in ("-", "—"):
        return 0
    m = re.search(r"(\d{1,2})\s*(?:歲|岁|Y\.?O\.?)?", raw, re.I)
    if m:
        return int(m.group(1))
    return _safe_int(raw)


def _parse_age_sex_cell(raw: str) -> tuple[int, str]:
    """Parse combined cells like '4歲 閹' or '5雌'."""
    if not raw or raw in ("-", "—"):
        return 0, ""
    sex = _parse_horse_sex(raw)
    age = _parse_horse_age(raw)
    return age, sex


def merge_runner_profile(target: dict, source: dict) -> bool:
    """Merge racecard fields into a runner; returns True if target changed."""
    changed = False
    for key in ("name", "jockey", "trainer", "recent_form", "horse_code"):
        if source.get(key) and not target.get(key):
            target[key] = source[key]
            changed = True
    src_rating = int(source.get("rating") or 0)
    if src_rating > 0 and int(target.get("rating") or 0) < src_rating:
        target["rating"] = src_rating
        changed = True
    src_age = int(source.get("age") or 0)
    if src_age > 0 and not int(target.get("age") or 0):
        target["age"] = src_age
        changed = True
    if source.get("sex") and not target.get("sex"):
        target["sex"] = source["sex"]
        changed = True
    return changed


def build_horses_index_from_meeting(meeting: dict) -> list[dict]:
    horses_index: dict[str, dict] = {}
    for race in meeting.get("races") or []:
        for r in race.get("runners") or []:
            code = r.get("horse_code") or r.get("name")
            if not code:
                continue
            entry = {
                "name": r.get("name"),
                "rating": r.get("rating", 0),
                "age": r.get("age", 0),
                "sex": r.get("sex", ""),
                "trainer": r.get("trainer", ""),
                "recent_form": r.get("recent_form", ""),
                "horse_code": r.get("horse_code") or code,
            }
            if code not in horses_index:
                horses_index[code] = entry
            else:
                merge_runner_profile(horses_index[code], entry)
    return sorted(horses_index.values(), key=lambda h: -int(h.get("rating") or 0))


def _parse_race_meta(text: str) -> dict:
    meta: dict[str, Any] = {}
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        meta["date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"第([一二三四五六七八九十\d]+)班", text)
    if m:
        meta["class"] = f"第{m.group(1)}班"
    m = re.search(r"(\d{3,4})米", text)
    if m:
        meta["distance_m"] = int(m.group(1))
    if "沙田" in text:
        meta["venue_code"] = "ST"
    elif "跑馬地" in text or "跑马地" in text:
        meta["venue_code"] = "HV"
    meta["track_type"] = "泥地" if "全天候" in text or "泥" in text else "草地"
    m = re.search(r"(好地至快地|好地|快地|黏地|軟地|大爛地|濕慢地|好地至快)", text)
    meta["going"] = m.group(1) if m else ""
    m = re.search(r"(\d{1,2}:\d{2})", text)
    if m:
        meta["start_time"] = m.group(1)
    m = re.search(r"第\s*(\d+)\s*場", text)
    if m:
        meta["race_no"] = int(m.group(1))
    return meta


def parse_racecard_html(html: str, race_date: str, venue_code: str, race_no: int) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    meta = _parse_race_meta(text)
    meta.setdefault("date", race_date)
    meta.setdefault("venue_code", venue_code.upper())
    meta.setdefault("race_no", race_no)

    runners: list[dict] = []
    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 2:
            continue
        header = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        joined = "".join(header)
        if not any(k in joined for k in RUNNER_HEADER_KEYS):
            continue

        col_no = _find_header_col(header, "馬號", "马号", "Horse No.") or 0
        col_last6 = _find_header_col(header, "6次近績", "6次近绩", "Last 6 Runs") or 1
        col_name = _find_header_col(header, "馬名", "马名", "Horse") or 3
        col_brand = _find_header_col(header, "烙號", "烙号", "Brand No.") or 4
        col_wt = _find_header_col(header, "負磅", "负磅", "Wt.") or 5
        col_jockey = _find_header_col(header, "騎師", "骑师", "Jockey") or 6
        col_draw = _find_header_col(header, "檔位", "档位", "Draw") or 8
        col_trainer = _find_header_col(header, "練馬師", "练马师", "Trainer") or 9
        col_rating = _find_rating_col(header)
        col_age = _find_header_col(header, "馬齡", "马龄", "年龄", "年齡", "Age")
        col_sex = _find_header_col(header, "性別", "性别", "Sex")
        col_age_sex = _find_header_col(header, "馬齡/性別", "马龄/性别", "馬齡性別", "Age/Sex")
        col_wt_delta = _find_header_col(
            header, "排位體重+/-", "排位体重+/-", "Wt.+/-", "馬匹體重+/-"
        )

        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 10:
                continue
            horse_no = _safe_int(_cell_at(cells, col_no))
            if horse_no <= 0:
                continue
            last6_raw = _cell_at(cells, col_last6)
            last6 = parse_last6run(last6_raw.replace("/", "-"))
            name = _cell_at(cells, col_name)
            draw = _safe_int(_cell_at(cells, col_draw))
            rating_raw = _cell_at(cells, col_rating) if col_rating is not None else ""
            rating = _safe_int(rating_raw)
            if rating <= 0:
                col_intl = _find_header_col(header, "國際評分", "国际评分", "Int'l Rtg.")
                if col_intl is not None and col_intl != col_rating:
                    rating = _safe_int(_cell_at(cells, col_intl))
            weight = float(_safe_int(_cell_at(cells, col_wt)))
            weight_delta = _parse_weight_delta(_cell_at(cells, col_wt_delta, "0"))
            jockey = _cell_at(cells, col_jockey)
            trainer = _cell_at(cells, col_trainer)
            if col_age_sex is not None and col_age is None and col_sex is None:
                age, sex = _parse_age_sex_cell(_cell_at(cells, col_age_sex))
            else:
                age = _parse_horse_age(_cell_at(cells, col_age))
                sex = _parse_horse_sex(_cell_at(cells, col_sex))
                if (not age or not sex) and col_age_sex is not None:
                    a2, s2 = _parse_age_sex_cell(_cell_at(cells, col_age_sex))
                    age = age or a2
                    sex = sex or s2
            distance_m = int(meta.get("distance_m") or 1200)
            stats = compute_runner_stats(last6, distance_m, draw)
            recent_form = last6_raw.replace("/", "-") if last6_raw else ""
            runners.append({
                "horse_no": horse_no,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "draw": draw,
                "weight": weight,
                "weight_delta": weight_delta,
                "rating": rating,
                "age": age,
                "sex": sex,
                "recent_form": recent_form,
                "stats": stats,
                "odds": 99.0,
                "tags": [],
                "horse_code": _cell_at(cells, col_brand),
            })
        if runners:
            break

    if not runners:
        return None

    meeting_id = meeting_id_from(meta["date"], meta["venue_code"])
    race_id = f"{meeting_id}-r{race_no}"
    dist_cat = distance_category(int(meta.get("distance_m") or 1200))
    risk = "high" if len(runners) >= 12 else "medium"
    return {
        "id": race_id,
        "meeting_id": meeting_id,
        "race_no": race_no,
        "name": f"第{race_no}场",
        "distance_m": int(meta.get("distance_m") or 1200),
        "distance_category": dist_cat,
        "class": meta.get("class") or "",
        "track_type": meta.get("track_type") or "草地",
        "start_time": meta.get("start_time") or "",
        "prize_hkd": 0,
        "risk_level": risk,
        "going": meta.get("going") or "",
        "runners": runners,
    }


def parse_racecard_index(html: str) -> dict | None:
    """Parse default RaceCard page for upcoming meeting summary."""
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    meta = _parse_race_meta(text)
    if not meta.get("date") or not meta.get("venue_code"):
        m = re.search(r"(\d{1,2})月(\d{1,2})日\s*-\s*(沙田|跑馬地|跑马地)", text)
        if m:
            year = datetime.now(ZoneInfo("Asia/Hong_Kong")).year
            meta["date"] = f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            meta["venue_code"] = "ST" if "沙田" in m.group(3) else "HV"
    race_count = _extract_race_count_from_text(text)
    if not meta.get("date"):
        return None
    venue_code = meta.get("venue_code") or "ST"
    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    meeting_id = meeting_id_from(meta["date"], venue_code)
    return {
        "id": meeting_id,
        "date": meta["date"],
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "race_count": race_count,
    }


def _extract_race_count_from_text(text: str) -> int:
    m = re.search(r"共\s*(\d+)\s*場", text)
    return int(m.group(1)) if m else 0


def _meeting_stub(date_str: str, venue_code: str, *, race_count: int = 0, featured: bool = False) -> dict:
    venue_code = venue_code.upper()
    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    return {
        "id": meeting_id_from(date_str, venue_code),
        "date": date_str,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "race_count": race_count,
        "featured": featured,
    }


def parse_results_all_dates(html: str, limit: int = 30) -> list[str]:
    """Recent meeting dates from ResultsAll.aspx dropdown (newest first)."""
    soup = BeautifulSoup(html, "html.parser")
    dates: list[str] = []
    seen: set[str] = set()
    for sel in soup.select("select"):
        options = sel.select("option")
        if len(options) < 10:
            continue
        for opt in options:
            raw = (opt.get("value") or opt.get_text(strip=True) or "").strip()
            date_raw = raw
            try:
                data = json.loads(raw)
                date_raw = data.get("date") or date_raw
            except (json.JSONDecodeError, TypeError):
                pass
            dm = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_raw or "")
            if not dm:
                continue
            iso = f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}"
            if iso in seen:
                continue
            seen.add(iso)
            dates.append(iso)
            if len(dates) >= limit:
                return dates
        if dates:
            return dates
    return dates


def parse_results_all_meetings(html: str, limit: int = 30) -> list[dict]:
    """Extract recent local meeting dates from ResultsAll page."""
    found: list[dict] = []
    seen: set[str] = set()
    for d in parse_results_all_dates(html, limit=limit):
        mid = meeting_id_from(d, "ST")
        if mid in seen:
            continue
        seen.add(mid)
        found.append(_meeting_stub(d, "ST"))
    if found:
        return found

    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select("table tr"):
        text = row.get_text(" ", strip=True)
        if "沙田" not in text and "跑馬" not in text and "跑马" not in text:
            continue
        dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if not dm:
            continue
        d = f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}"
        venue_code = "ST" if "沙田" in text else "HV"
        mid = meeting_id_from(d, venue_code)
        if mid in seen:
            continue
        seen.add(mid)
        venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
        found.append({
            "id": mid,
            "date": d,
            "venue": venue_zh,
            "venue_en": venue_en,
            "venue_code": venue_code,
        })
        if len(found) >= limit:
            break
    return found


async def resolve_venue_for_date(client: HkjcClient, meeting_date: str) -> str | None:
    """Probe ST/HV LocalResults to find which venue ran on this date."""
    rd = date.fromisoformat(meeting_date)
    for venue_code in ("ST", "HV"):
        try:
            res = await client.fetch_race_result(rd, venue_code, 1)
            if res and res.get("finishers"):
                return venue_code
        except Exception:
            continue
        await asyncio.sleep(0.08)
    return None


def _race_from_local_result(result: dict, meeting_date: str, venue_code: str) -> dict:
    """Minimal race card shape from LocalResults payload."""
    finishers = result.get("finishers") or []
    race_no = int(result["race_no"])
    meeting_id = meeting_id_from(meeting_date, venue_code)
    distance_m = int(result.get("distance_m") or 1200)
    runners = []
    for f in finishers:
        horse_no = int(f.get("horse_no") or 0)
        placing = int(f.get("placing") or 9)
        stats = {
            "win_rate_10": 0.2 if placing == 1 else 0.1,
            "place_rate_10": 0.5 if placing <= 3 else 0.25,
            "distance_fit": 0.85,
            "track_fit": 0.85,
            "draw_fit": 0.8,
            "jockey_pair_rate": 0.15,
            "trainer_rate": 0.15,
        }
        runners.append({
            "horse_no": horse_no,
            "name": f.get("name") or "",
            "jockey": f.get("jockey") or "",
            "trainer": f.get("trainer") or "",
            "draw": int(f.get("draw") or 0),
            "weight": 0,
            "weight_delta": 0,
            "rating": 0,
            "age": 0,
            "sex": "",
            "recent_form": str(placing),
            "stats": stats,
            "odds": float(f.get("odds") or 10.0),
            "tags": [],
            "actual_placing": placing,
        })
    return {
        "id": f"{meeting_id}-r{race_no}",
        "meeting_id": meeting_id,
        "race_no": race_no,
        "name": f"第{race_no}场",
        "distance_m": distance_m,
        "distance_category": distance_category(distance_m),
        "class": result.get("class") or "",
        "track_type": result.get("track_type") or "草地",
        "start_time": "",
        "prize_hkd": 0,
        "risk_level": "medium",
        "going": result.get("going") or "",
        "runners": runners,
    }


async def fetch_meeting_from_results(
    client: HkjcClient,
    meeting_date: str,
    venue_code: str,
    *,
    max_races: int = 12,
) -> dict | None:
    """Build meeting from official LocalResults (past race days)."""
    venue_code = venue_code.upper()
    rd = date.fromisoformat(meeting_date)
    races: list[dict] = []
    for race_no in range(1, max_races + 1):
        try:
            result = await client.fetch_race_result(rd, venue_code, race_no)
        except Exception:
            break
        if not result or not result.get("finishers"):
            break
        races.append(_race_from_local_result(result, meeting_date, venue_code))
        await asyncio.sleep(0.1)
    if not races:
        return None

    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    meeting_id = meeting_id_from(meeting_date, venue_code)
    return {
        "id": meeting_id,
        "date": meeting_date,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "track_type": races[0].get("track_type", "草地"),
        "track_rating": races[0].get("going", ""),
        "weather": "",
        "temperature_c": None,
        "race_count": len(races),
        "meeting_risk": "medium",
        "featured": False,
        "status": "RESULTS",
        "races": races,
        "horses_index": [],
        "source": "hkjc_results",
    }


async def fetch_meeting_from_html(
    client: HkjcClient,
    meeting_date: str,
    venue_code: str,
    *,
    max_races: int = 12,
) -> dict | None:
    """Build full meeting from per-race RaceCard pages."""
    venue_code = venue_code.upper()
    races: list[dict] = []
    horses_index: dict[str, dict] = {}

    for race_no in range(1, max_races + 1):
        race = await fetch_parsed_racecard(client, meeting_date, venue_code, race_no)
        if not race:
            break
        # Enrich odds from results if race already finished
        try:
            rd = date.fromisoformat(meeting_date)
            result = await client.fetch_race_result(rd, venue_code, race_no)
            if result:
                odds_map = {f["horse_no"]: f.get("odds") for f in result.get("finishers") or []}
                for runner in race["runners"]:
                    if odds_map.get(runner["horse_no"]):
                        runner["odds"] = float(odds_map[runner["horse_no"]])
        except Exception:
            pass
        races.append(race)
        for r in race["runners"]:
            code = r.get("horse_code") or r.get("name")
            if code and code not in horses_index:
                horses_index[code] = {
                    "name": r["name"],
                    "rating": r["rating"],
                    "age": r["age"],
                    "sex": r["sex"],
                    "trainer": r["trainer"],
                    "recent_form": r["recent_form"],
                    "horse_code": r.get("horse_code"),
                }
        await asyncio.sleep(0.12)

    if not races:
        return None

    venue_zh, venue_en = VENUE_LABELS.get(venue_code, (venue_code, venue_code))
    meeting_id = meeting_id_from(meeting_date, venue_code)
    return {
        "id": meeting_id,
        "date": meeting_date,
        "venue": venue_zh,
        "venue_en": venue_en,
        "venue_code": venue_code,
        "track_type": races[0].get("track_type", "草地"),
        "track_rating": races[0].get("going", ""),
        "weather": "",
        "temperature_c": None,
        "race_count": len(races),
        "meeting_risk": "medium",
        "featured": True,
        "status": "ACTIVE",
        "races": races,
        "horses_index": sorted(horses_index.values(), key=lambda h: -h.get("rating", 0)),
        "source": "hkjc_html",
    }


def parse_entries_index(html: str) -> dict | None:
    """Next declared meeting from official entries page."""
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if not m:
        return None
    meeting_date = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    venue_code = ""
    if re.search(r"跑馬地|跑马地", text):
        venue_code = "HV"
    elif "沙田" in text:
        venue_code = "ST"
    if not venue_code:
        return None
    race_count = _extract_race_count_from_text(text)
    return _meeting_stub(meeting_date, venue_code, race_count=race_count)


async def probe_racecard_meeting(
    client: HkjcClient,
    meeting_date: str,
    venue_code: str,
) -> dict | None:
    """Return meeting stub if RaceCard exists for the requested date/venue."""
    venue_code = venue_code.upper()
    race = await fetch_parsed_racecard(client, meeting_date, venue_code, 1)
    if not race or not race.get("runners"):
        return None
    meta_date = meeting_date
    if race.get("meeting_id"):
        parts = race["meeting_id"].rsplit("-", 1)
        if len(parts) == 2 and len(parts[0]) == 8:
            meta_date = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]}"
    if meta_date != meeting_date:
        return None
    race_count = 0
    try:
        idx_html = await client.fetch_html(f"{HKJC_LOCAL_INFO}/racecard")
        idx = parse_racecard_index(idx_html)
        if idx and idx.get("id") == meeting_id_from(meeting_date, venue_code):
            race_count = int(idx.get("race_count") or 0)
    except Exception:
        pass
    if not race_count:
        race_count = 8
    return _meeting_stub(meeting_date, venue_code, race_count=race_count)


async def discover_upcoming_meetings(
    client: HkjcClient,
    *,
    days: int = 28,
) -> list[dict]:
    """Scan the next week for published RaceCard meetings."""
    hk_today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    found: list[dict] = []
    seen: set[str] = set()
    for offset in range(0, days + 1):
        d = (hk_today + timedelta(days=offset)).isoformat()
        for venue_code in ("ST", "HV"):
            stub = await probe_racecard_meeting(client, d, venue_code)
            if not stub:
                continue
            mid = stub["id"]
            if mid in seen:
                continue
            seen.add(mid)
            found.append({**stub, "status": "UPCOMING", "featured": offset == 0})
            await asyncio.sleep(0.08)
    return found


async def discover_scheduled_meetings(client: HkjcClient) -> list[dict]:
    """Meetings declared on entries page (next declared race day)."""
    found: list[dict] = []
    try:
        html = await client.fetch_html(f"{HKJC_LOCAL_INFO}/entries")
        entry = parse_entries_index(html)
        if not entry:
            return found
        rd = date.fromisoformat(entry["date"])
        if rd < datetime.now(HK_TZ).date():
            return found
        stub = await probe_racecard_meeting(client, entry["date"], entry["venue_code"])
        if stub:
            found.append({**stub, "status": "UPCOMING", "race_count": entry.get("race_count", 0)})
        else:
            found.append({**entry, "status": "SCHEDULED", "race_count": 0})
    except Exception:
        pass
    return found


async def discover_meetings(client: HkjcClient, *, limit: int = 25) -> list[dict]:
    meetings: list[dict] = []
    seen: set[str] = set()

    try:
        index_html = await client.fetch_html(f"{HKJC_LOCAL_INFO}/racecard")
        index = parse_racecard_index(index_html)
        if index:
            meetings.append({
                **index,
                "race_count": index.get("race_count") or index.get("race_count_hint") or 0,
                "featured": True,
                "status": "ACTIVE",
            })
            seen.add(index["id"])
    except Exception:
        pass

    if not meetings:
        try:
            index_html = await client.fetch_html(f"{HKJC_RACING_BASE}/RaceCard.aspx")
            index = parse_racecard_index(index_html)
            if index and index["id"] not in seen:
                meetings.append({
                    **index,
                    "race_count": index.get("race_count") or index.get("race_count_hint") or 0,
                    "featured": True,
                    "status": "ACTIVE",
                })
                seen.add(index["id"])
        except Exception:
            pass

    try:
        for item in await discover_scheduled_meetings(client):
            if item["id"] not in seen:
                meetings.append(item)
                seen.add(item["id"])
    except Exception:
        pass

    try:
        upcoming = await discover_upcoming_meetings(client, days=14)
        for item in upcoming:
            if item["id"] not in seen:
                meetings.append(item)
                seen.add(item["id"])
    except Exception:
        pass

    date_candidates: list[str] = []
    try:
        all_html = await client.fetch_html(f"{HKJC_RACING_BASE}/ResultsAll.aspx")
        date_candidates = parse_results_all_dates(all_html, limit=limit)
    except Exception:
        pass

    for d in date_candidates:
        if len(meetings) >= limit:
            break
        venue_code = await resolve_venue_for_date(client, d)
        if not venue_code:
            continue
        mid = meeting_id_from(d, venue_code)
        if mid in seen:
            continue
        seen.add(mid)
        meetings.append({**_meeting_stub(d, venue_code), "status": "RESULTS"})

    return meetings


async def enrich_meeting_from_racecard_html(
    client: HkjcClient,
    meeting: dict,
    *,
    max_races: int = 12,
) -> bool:
    """Fill age/sex/rating from official RaceCard HTML (GraphQL omits these)."""
    meeting_date = meeting.get("date") or ""
    venue_code = (meeting.get("venue_code") or "").upper()
    if not meeting_date or not venue_code or not meeting.get("races"):
        return False

    changed = False
    for race in meeting.get("races") or []:
        race_no = int(race.get("race_no") or 0)
        if race_no <= 0 or race_no > max_races:
            continue
        parsed = await fetch_parsed_racecard(client, meeting_date, venue_code, race_no)
        if not parsed:
            continue
        by_no = {int(r["horse_no"]): r for r in parsed.get("runners") or []}
        for runner in race.get("runners") or []:
            src = by_no.get(int(runner.get("horse_no") or 0))
            if src and merge_runner_profile(runner, src):
                changed = True
        await asyncio.sleep(0.08)

    if changed:
        meeting["horses_index"] = build_horses_index_from_meeting(meeting)
    return changed


async def fetch_meeting_with_graphql_fallback(
    client: HkjcClient,
    meeting_date: str,
    venue_code: str,
) -> dict | None:
    """Try GraphQL first; fall back to HTML RaceCard scraping."""
    try:
        raw = await client.fetch_meeting(meeting_date, venue_code.upper())
        if raw and raw.get("races"):
            odds_by_race: dict[int, dict[int, float]] = {}
            for race in raw.get("races") or []:
                race_no = int(race.get("no") or 0)
                if race_no:
                    try:
                        odds_by_race[race_no] = await client.fetch_win_odds(
                            meeting_date, venue_code.upper(), race_no
                        )
                    except Exception:
                        odds_by_race[race_no] = {}
            meeting = map_graphql_meeting(raw, odds_by_race)
            meeting["source"] = "hkjc_graphql"
            await enrich_meeting_from_racecard_html(client, meeting)
            return meeting
    except Exception:
        pass
    meeting = await fetch_meeting_from_html(client, meeting_date, venue_code)
    if meeting and meeting.get("race_count", 0) > 0:
        return meeting
    return await fetch_meeting_from_results(client, meeting_date, venue_code)
