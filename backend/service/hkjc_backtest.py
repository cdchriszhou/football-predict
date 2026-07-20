"""Compute HKJC model backtest from official stored race results."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.hkjc_client import compute_runner_stats
from crawler.hkjc_scraper import VENUE_LABELS, parse_last6run
from db.models import HkjcRaceResult
from service.hkjc_engine import analyze_race
from service.hkjc_sync import (
    _load_meeting_row,
    meeting_id_from,
    result_to_race_payload,
)

_NEUTRAL_STATS = {
    "win_rate_10": 0.12,
    "place_rate_10": 0.28,
    "distance_fit": 0.75,
    "track_fit": 0.75,
    "draw_fit": 0.75,
    "jockey_pair_rate": 0.15,
    "trainer_rate": 0.15,
}

# Meeting payloads built only from LocalResults must not drive model ranking.
_RESULT_ONLY_SOURCES = frozenset({"hkjc_results"})


def _is_placing_only_form(form: str) -> bool:
    """result_to_race_payload sets recent_form=str(placing) — that leaks the winner."""
    return bool(re.fullmatch(r"\d{1,2}", (form or "").strip()))


def prepare_race_for_backtest(race: dict, *, pre_race: bool = True) -> dict:
    """Strip post-race fields; remove closing odds / result-page form leakage."""
    race = deepcopy(race)
    race.pop("is_finished", None)
    race.pop("winner_horse_no", None)
    distance_m = int(race.get("distance_m") or 1200)
    for runner in race.get("runners") or []:
        runner.pop("actual_placing", None)
        runner.pop("placing", None)
        form_raw = str(runner.get("recent_form") or "").strip()
        if not pre_race or _is_placing_only_form(form_raw):
            form_raw = ""
        if pre_race and form_raw and form_raw not in ("-", "—"):
            last6 = parse_last6run(form_raw.replace("/", "-"))
            if last6:
                runner["stats"] = compute_runner_stats(
                    last6, distance_m, int(runner.get("draw") or 0)
                )
            else:
                runner["stats"] = dict(_NEUTRAL_STATS)
        else:
            runner["stats"] = dict(_NEUTRAL_STATS)
        # Closing odds on the results page make the favourite == winner too often.
        if pre_race:
            try:
                runner["odds"] = float(runner.get("odds") or 99.0)
            except (TypeError, ValueError):
                runner["odds"] = 99.0
        else:
            runner["odds"] = 99.0
        if not pre_race:
            runner["rating"] = int(runner.get("rating") or 0)
    race["_backtest_pre_race"] = pre_race
    return race


async def _race_for_backtest(
    db: AsyncSession,
    *,
    meeting_date: str,
    venue_code: str,
    race_no: int,
    result: dict,
) -> dict | None:
    """Use pre-race racecard cache only; never rank on merged result-page rows."""
    meeting_id = meeting_id_from(meeting_date, venue_code.upper())
    meeting = await _load_meeting_row(db, meeting_id)
    if meeting:
        src = (meeting.get("source") or "").lower()
        if src not in _RESULT_ONLY_SOURCES:
            for race in meeting.get("races") or []:
                if int(race.get("race_no") or 0) == race_no:
                    runners = race.get("runners") or []
                    if len(runners) >= 3:
                        return prepare_race_for_backtest(race, pre_race=True)
    try:
        built = result_to_race_payload(result)
    except (KeyError, ValueError, TypeError):
        return None
    if len(built.get("runners") or []) < 3:
        return None
    # Limited: no racecard in DB — evaluate on rating/draw/jockey only, no result odds/form.
    return prepare_race_for_backtest(built, pre_race=False)


def _meeting_detail_key(meeting_date: str, venue_code: str) -> str:
    return f"{meeting_date}|{venue_code.upper()}"


def _winner_name(result: dict, winner_no: int) -> str:
    for f in result.get("finishers") or []:
        if int(f.get("horse_no") or 0) == int(winner_no):
            return f.get("name") or ""
    return ""


def _format_odds(value) -> float | None:
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    if odds <= 0 or odds >= 90:
        return None
    return round(odds, 1)


def _winner_odds(result: dict, winner_no: int) -> float | None:
    for f in result.get("finishers") or []:
        if int(f.get("horse_no") or 0) == int(winner_no):
            return _format_odds(f.get("odds"))
    return None


async def compute_backtest(db: AsyncSession, *, max_meeting_days: int = 30) -> dict:
    rows = (await db.execute(
        select(HkjcRaceResult).order_by(HkjcRaceResult.meeting_date.desc())
    )).scalars().all()

    if not rows:
        return {
            "period": "暂无历史赛果",
            "races_evaluated": 0,
            "win_hit_rate": 0.0,
            "place_top3_rate": 0.0,
            "high_confidence_hit": 0.0,
            "model_version": "hkjc-live-v1",
            "last_retrain": None,
            "data_source": "香港赛马会官网 LocalResults",
            "notes": [
                "回测基于已同步的官方赛果页面数据",
                "需先同步历史赛果后才会产生评估指标",
                "指标仅供模型参考，不构成投注建议",
            ],
            "meetings": [],
        }

    win_hits = 0
    top3_hits = 0
    high_conf_hits = 0
    high_conf_total = 0
    evaluated = 0
    by_date: dict[str, dict[str, int]] = {}
    meetings_map: dict[str, dict] = {}

    for row in rows:
        try:
            result = json.loads(row.payload)
        except json.JSONDecodeError:
            continue
        if not result.get("finishers"):
            continue
        winner = result.get("winner_horse_no")
        if not winner:
            continue

        race = await _race_for_backtest(
            db,
            meeting_date=row.meeting_date,
            venue_code=row.venue_code,
            race_no=row.race_no,
            result=result,
        )
        if not race:
            continue

        analysis = analyze_race(race, use_ai=False)
        if analysis.get("mode") == "result":
            continue
        rankings = analysis.get("rankings") or []
        if not rankings:
            continue

        evaluated += 1
        top_pick = rankings[0]
        actual_top3 = {
            int(f["horse_no"])
            for f in result["finishers"]
            if int(f.get("placing") or 99) <= 3
        }
        if int(top_pick.get("horse_no")) == int(winner):
            win_hits += 1
        if int(top_pick.get("horse_no")) in actual_top3:
            top3_hits += 1

        primary = analysis.get("picks", {}).get("primary") or []
        if primary:
            high_conf_total += 1
            if any(int(p.get("horse_no")) == int(winner) for p in primary):
                high_conf_hits += 1

        bucket = by_date.setdefault(row.meeting_date, {"evaluated": 0, "win_hits": 0})
        bucket["evaluated"] += 1
        if int(top_pick.get("horse_no")) == int(winner):
            bucket["win_hits"] += 1

        mkey = _meeting_detail_key(row.meeting_date, row.venue_code)
        venue_code = row.venue_code.upper()
        venue_zh = VENUE_LABELS.get(venue_code, (venue_code, venue_code))[0]
        meeting = meetings_map.setdefault(
            mkey,
            {
                "meeting_date": row.meeting_date,
                "venue_code": venue_code,
                "venue": venue_zh,
                "win_hits": 0,
                "evaluated": 0,
                "races": [],
            },
        )
        win_hit = int(top_pick.get("horse_no")) == int(winner)
        in_top3 = int(top_pick.get("horse_no")) in actual_top3
        meeting["evaluated"] += 1
        if win_hit:
            meeting["win_hits"] += 1
        pre_race = bool(race.get("_backtest_pre_race"))
        raw_wp = float(top_pick.get("win_probability") or 0)
        win_pct = round(raw_wp * 100, 1) if raw_wp <= 1 else round(raw_wp, 1)
        model_odds = _format_odds(top_pick.get("odds")) if pre_race else None
        meeting["races"].append({
            "race_no": int(row.race_no),
            "race_name": race.get("name") or f"第{row.race_no}场",
            "model_horse_no": int(top_pick.get("horse_no") or 0),
            "model_horse_name": top_pick.get("name") or "",
            "model_win_probability": win_pct,
            "model_odds": model_odds,
            "winner_odds": _winner_odds(result, int(winner)),
            "actual_winner_no": int(winner),
            "actual_winner_name": _winner_name(result, int(winner)),
            "win_hit": win_hit,
            "top_pick_in_top3": in_top3,
            "has_primary_pick": bool(primary),
            "data_quality": "racecard" if pre_race else "limited",
        })

    meetings_out: list[dict] = []
    for m in meetings_map.values():
        m["races"].sort(key=lambda r: r["race_no"])
        m["win_hit_rate"] = (
            round(m["win_hits"] / m["evaluated"] * 100, 1) if m["evaluated"] else 0.0
        )
        rc = sum(1 for r in m["races"] if r.get("data_quality") == "racecard")
        m["racecard_races"] = rc
        m["limited_races"] = m["evaluated"] - rc
        meetings_out.append(m)
    meetings_out.sort(key=lambda x: x["meeting_date"], reverse=True)
    if max_meeting_days > 0:
        meetings_out = meetings_out[:max_meeting_days]

    win_rate = round(win_hits / evaluated * 100, 1) if evaluated else 0.0
    top3_rate = round(top3_hits / evaluated * 100, 1) if evaluated else 0.0
    high_rate = round(high_conf_hits / high_conf_total * 100, 1) if high_conf_total else 0.0

    dates = sorted({r.meeting_date for r in rows})
    period = f"{dates[-1]} ~ {dates[0]}" if dates else "—"

    recent_samples = []
    for d in sorted(by_date.keys(), reverse=True)[:5]:
        b = by_date[d]
        if b["evaluated"]:
            pct = round(b["win_hits"] / b["evaluated"] * 100, 1)
            recent_samples.append(f"{d}: 独赢命中 {b['win_hits']}/{b['evaluated']} ({pct}%)")

    notes = [
        "回测不使用真实名次；有排位表缓存的场次用赛前赔率/近绩，仅赛果的场次不用赛后赔率（避免假命中）",
        "若模型首选与冠军长期完全相同，请确认已同步该赛事日的排位表（仪表盘「同步官网数据」）",
        "独赢命中率 = 模型排名第一的马是否跑赢冠军",
        "头号入三甲率 = 模型排名第一的马是否跑进前三名",
        "明细中「赛前」= 排位表数据；「受限」= 仅有赛果页、不含赛后赔率",
        "赔率列：左为模型首选赛前独赢赔率，右为冠军赛果独赢赔率（斜杠分隔）",
    ]
    if recent_samples:
        notes.append("近期样本：" + "；".join(recent_samples))

    return {
        "period": period,
        "races_evaluated": evaluated,
        "win_hit_rate": win_rate,
        "place_top3_rate": top3_rate,
        "high_confidence_hit": high_rate,
        "model_version": "hkjc-live-v1",
        "last_retrain": datetime.utcnow().isoformat() + "Z",
        "data_source": "香港赛马会官网 LocalResults",
        "notes": notes,
        "recent_by_date": recent_samples,
        "meetings": meetings_out,
    }
