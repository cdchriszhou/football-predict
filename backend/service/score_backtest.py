"""Score prediction backtest — replay CRS pipeline on finished matches."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.team_crawler import TEAM_DATA
from db.redis_client import cache_delete, cache_get, cache_set
from data.worldcup_history import HISTORICAL_MATCHES, rank_to_abilities
from data.worldcup_schedule_lookup import canonical_kickoff_beijing
from db.models import Match, Odds, Prediction
from utils.datetime_helpers import china_today
from utils.score_prediction import normalize_score_prediction
from service.score_pick import (
    refine_wdl_after_score_pick,
    run_full_score_pipeline,
    score_matches_pick,
)
from service.rule_engine import RuleEngine

DISCLAIMER = (
    "回测使用赛前 CRS 比分赔率与胜平负概率，在已知赛果的场次上重跑当前算法，"
    "用于评估逻辑可靠性，不代表未来场次命中率。"
)

NOTES = [
    "首推：CRS 锚定管线输出的第一推荐比分。",
    "三选：首推、次推与冷门选项中任一命中即计为命中（含胜/平/负其它桶）。",
    "仅纳入已有 CRS 比分赔率且赛果已确认的场次。",
    "胜平负概率优先取自数据库预测记录，并与欧赔隐含平局做纠偏。",
]

DAILY_REPORT_CACHE_TTL = 300
DAILY_REPORT_CACHE_PREFIX = "score_backtest_daily:v5:"


def _history_row(team_a: str, team_b: str, year: int = 2026) -> dict | None:
    for m in HISTORICAL_MATCHES:
        if m.get("year") == year and m.get("team_a") == team_a and m.get("team_b") == team_b:
            return m
    return None


def _expected_goals(team_a: str, team_b: str) -> tuple[float, float]:
    a = rank_to_abilities(TEAM_DATA.get(team_a, {}).get("rank", 50))
    b = rank_to_abilities(TEAM_DATA.get(team_b, {}).get("rank", 50))
    return round((a["attack"] + b["defend"]) / 80, 2), round((b["attack"] + a["defend"]) / 80, 2)


def _correct_draw(wr: float, dr: float, lr: float, sp: dict | None) -> tuple[float, float, float]:
    if not sp or not sp.get("draw"):
        return wr, dr, lr
    w, d, l = sp.get("win_win"), sp.get("draw"), sp.get("win_lose")
    if not (w and d and l):
        return wr, dr, lr
    over = 1 / w + 1 / d + 1 / l
    m_draw = (1 / d) / over * 100
    if abs(dr - m_draw) <= 15:
        return wr, dr, lr
    correction = min(0.5, 0.25 + (abs(dr - m_draw) - 15) / 60)
    new_dr = (1 - correction) * dr + correction * m_draw
    shift = new_dr - dr
    wr -= shift / 2
    lr -= shift / 2
    total = max(wr + new_dr + lr, 1)
    scale = 100 / total
    return wr * scale, new_dr * scale, lr * scale


def _parse_score_odds(raw: str | None) -> dict[str, float]:
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    data.pop("_meta", None)
    out: dict[str, float] = {}
    for k, v in data.items():
        if str(k).startswith("_"):
            continue
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _odds_meta_from_history(hist: dict | None) -> dict:
    if not hist:
        return {}
    euro = hist.get("european") or {}
    macau = hist.get("macau") or {}
    return {
        "win_win": euro.get("win_win"),
        "draw": euro.get("draw"),
        "win_lose": euro.get("win_lose"),
        "handicap": macau.get("handicap"),
    }


def _poisson_model_hints(exp_a: float, exp_b: float, draw_rate: float) -> list[str]:
    ranked = RuleEngine._score_probabilities(exp_a, exp_b, draw_rate=draw_rate)
    return [s for s, _ in ranked[:3]]


def run_score_prediction(
    team_a: str,
    team_b: str,
    crs: dict[str, float],
    wdl: tuple[float, float, float] | None,
    odds_meta: dict | None,
    *,
    stage: str | None = None,
    model_scores: list[str] | None = None,
) -> tuple[str, str, str | None, list[str]]:
    """Run full CRS score pick pipeline (same as production)."""
    wr, dr, lr = wdl if wdl else (50.0, 25.0, 25.0)
    sp = odds_meta or {}
    wr, dr, lr = _correct_draw(wr, dr, lr, sp)
    exp_a, exp_b = _expected_goals(team_a, team_b)
    ra = TEAM_DATA.get(team_a, {}).get("rank", 50)
    rb = TEAM_DATA.get(team_b, {}).get("rank", 50)
    hints = model_scores or _poisson_model_hints(exp_a, exp_b, dr)

    best, upset, picks, _ = run_full_score_pipeline(
        crs,
        win_rate=wr,
        draw_rate=dr,
        lose_rate=lr,
        expected_a=exp_a,
        expected_b=exp_b,
        model_scores=hints,
        stage=stage,
        sp_win=sp.get("win_win"),
        sp_draw=sp.get("draw"),
        sp_lose=sp.get("win_lose"),
        handicap=sp.get("handicap"),
        rank_a=ra,
        rank_b=rb,
    )
    wr, dr, lr = refine_wdl_after_score_pick(best, wr, dr, lr)
    from service.score_pick import reconcile_wdl_with_score_picks
    wr, dr, lr = reconcile_wdl_with_score_picks(best, wr, dr, lr)
    p1 = best[0] if best else "?"
    p2 = best[1] if len(best) > 1 else "-"
    return p1, p2, upset, picks


def _picks_from_db_prediction(pred_row) -> tuple[str, str, str | None, list[str]] | None:
    """Use published prediction scores when stored in DB (matches what users saw pre-match)."""
    if not pred_row or not pred_row.best_score:
        return None
    raw = pred_row.best_score
    scores: list[str] = []
    upset: str | None = None
    if isinstance(raw, dict):
        scores = [s for s in (raw.get("scores") or []) if s and s != "?"]
        u = raw.get("upset")
        upset = u if u and u != "?" else None
    elif isinstance(raw, list):
        scores = [s for s in raw if s and s != "?"]
    elif isinstance(raw, str):
        if raw.startswith("{") or raw.startswith("["):
            try:
                parsed = json.loads(raw)
                return _picks_from_db_prediction(type("P", (), {"best_score": parsed})())
            except json.JSONDecodeError:
                pass
        elif raw and raw != "?":
            scores = [raw]
    else:
        return None
    norm = normalize_score_prediction(scores, upset)
    best = norm["best_scores"]
    upset_val = norm.get("upset_score")
    if not best:
        return None
    p1 = best[0]
    p2 = best[1] if len(best) > 1 else "-"
    all_picks = best + ([upset_val] if upset_val else [])
    return p1, p2, upset_val, all_picks


def _evaluate_match(
    *,
    team_a: str,
    team_b: str,
    actual: str,
    crs: dict[str, float],
    wdl: tuple[float, float, float] | None,
    odds_meta: dict | None,
    match_id: int | None = None,
    match_time: datetime | None = None,
    stage: str = "",
    group_name: str | None = None,
    matchday: int | None = None,
    location: str | None = None,
    published_picks: tuple[str, str, str | None, list[str]] | None = None,
) -> dict | None:
    if not crs:
        return None
    if published_picks:
        p1, p2, upset, all_picks = published_picks
        pick_source = "published"
    else:
        p1, p2, upset, all_picks = run_score_prediction(
            team_a, team_b, crs, wdl, odds_meta, stage=stage or None,
        )
        pick_source = "replay"
    primary_hit = score_matches_pick(actual, p1, crs)
    triple_hit = any(score_matches_pick(actual, p, crs) for p in all_picks if p)
    return {
        "match_id": match_id,
        "team_a": team_a,
        "team_b": team_b,
        "actual_score": actual,
        "primary_pick": p1,
        "secondary_pick": p2,
        "upset_pick": upset,
        "primary_hit": primary_hit,
        "triple_hit": triple_hit,
        "pick_source": pick_source,
        "match_time": match_time.isoformat() if match_time else None,
        "stage": stage,
        "group_name": group_name,
        "matchday": matchday,
        "location": location,
        "has_crs": True,
    }


def _best_odds_with_crs(odds_rows: list) -> tuple[object | None, dict[str, float]]:
    """Prefer latest odds row that actually has CRS score lines."""
    for row in sorted(odds_rows, key=lambda o: o.id, reverse=True):
        crs = _parse_score_odds(row.score_odds)
        if crs:
            return row, crs
    latest = odds_rows[0] if odds_rows else None
    return latest, _parse_score_odds(latest.score_odds if latest else None)


async def _collect_evaluated_rows(
    db: AsyncSession,
    competition_slug: str = "worldcup-2026",
) -> tuple[list[dict], int, dict[str, int]]:
    """Evaluate finished matches with CRS odds; returns (rows, skipped, skip_reasons)."""
    rows = (await db.execute(
        select(Match).where(
            Match.competition_slug == competition_slug,
            Match.result_a.isnot(None),
            Match.result_b.isnot(None),
        ).order_by(Match.match_time.asc(), Match.id.asc())
    )).scalars().all()

    evaluated: list[dict] = []
    skipped = 0
    skip_reasons: dict[str, int] = {}

    for match in rows:
        actual = f"{match.result_a}:{match.result_b}"
        all_odds = (await db.execute(
            select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc())
        )).scalars().all()
        odds_row, crs = _best_odds_with_crs(list(all_odds))
        pred_row = (await db.execute(
            select(Prediction).where(Prediction.match_id == match.id)
            .order_by(Prediction.create_time.desc()).limit(1)
        )).scalar_one_or_none()

        odds_meta = None
        wdl = None

        if odds_row:
            odds_meta = {
                "win_win": odds_row.win_win,
                "draw": odds_row.draw,
                "win_lose": odds_row.win_lose,
                "handicap": odds_row.handicap,
            }
        if pred_row:
            wdl = (pred_row.win_rate, pred_row.draw_rate, pred_row.lose_rate)

        hist = _history_row(match.team_a, match.team_b)
        if not crs and hist:
            crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            odds_meta = odds_meta or _odds_meta_from_history(hist)
        if not wdl and hist:
            wdl = (50.0, 25.0, 25.0)

        kickoff = _resolve_kickoff(match.team_a, match.team_b, match.match_time, hist)
        published = _picks_from_db_prediction(pred_row)

        row = _evaluate_match(
            team_a=match.team_a,
            team_b=match.team_b,
            actual=actual,
            crs=crs,
            wdl=wdl,
            odds_meta=odds_meta,
            match_id=match.id,
            match_time=kickoff,
            stage=match.stage or "",
            group_name=match.group_name,
            matchday=match.matchday,
            location=match.location,
            published_picks=published,
        )
        if row:
            evaluated.append(row)
        else:
            skipped += 1
            reason = "no_crs" if not crs else "eval_failed"
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    seen = {(r["team_a"], r["team_b"]) for r in evaluated}
    for hist in HISTORICAL_MATCHES:
        if hist.get("year") != 2026:
            continue
        ta, tb = hist["team_a"], hist["team_b"]
        if (ta, tb) in seen:
            continue
        if hist.get("result_a") is None or hist.get("result_b") is None:
            continue
        crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
        if not crs:
            continue
        actual = f"{hist['result_a']}:{hist['result_b']}"
        row = _evaluate_match(
            team_a=ta,
            team_b=tb,
            actual=actual,
            crs=crs,
            wdl=(50.0, 25.0, 25.0),
            odds_meta=_odds_meta_from_history(hist),
            match_time=_resolve_kickoff(ta, tb, None, hist),
            stage=hist.get("stage") or "",
            group_name=hist.get("group_name"),
            matchday=hist.get("matchday"),
            location=hist.get("location"),
        )
        if row:
            evaluated.append(row)
            seen.add((ta, tb))

    evaluated.sort(key=lambda r: (r.get("match_time") or "", r.get("match_id") or 0))
    return evaluated, skipped, skip_reasons


def _parse_match_time(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip().replace(" ", "T")
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19])
    except (TypeError, ValueError):
        return None


def _resolve_kickoff(
    team_a: str,
    team_b: str,
    db_time: datetime | None = None,
    hist: dict | None = None,
) -> datetime | None:
    if db_time:
        return db_time
    if hist and hist.get("match_time"):
        parsed = _parse_match_time(hist.get("match_time"))
        if parsed:
            return parsed
    return canonical_kickoff_beijing(team_a, team_b)


def _match_beijing_date(row: dict) -> str | None:
    mt = row.get("match_time")
    if not mt:
        return None
    if isinstance(mt, datetime):
        return mt.strftime("%Y-%m-%d")
    s = str(mt).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _backtest_group_key_label(row: dict, *, prefer_date: bool) -> tuple[str, str]:
    """Group key/label for backtest UI — World Cup by Beijing date, leagues by matchday."""
    date_key = _match_beijing_date(row)
    md = row.get("matchday")
    if prefer_date and date_key:
        return f"d{date_key}", date_key
    if md:
        return f"md{md}", f"第{md}轮"
    if date_key:
        return f"d{date_key}", date_key
    stage = row.get("stage") or row.get("group_name") or "other"
    return f"stage_{stage}", row.get("stage") or "其它"


def _rate(hits: int, total: int) -> float:
    return round(hits / total * 100, 1) if total else 0.0


def build_daily_report(evaluated: list[dict], *, days: int = 14) -> dict:
    """Group evaluated rows by Beijing match date (match_time prefix)."""
    by_date: dict[str, dict] = {}
    for row in evaluated:
        date_key = _match_beijing_date(row)
        if not date_key:
            continue
        if date_key not in by_date:
            by_date[date_key] = {
                "date": date_key,
                "matchdays": set(),
                "matches": [],
                "primary_hits": 0,
                "triple_hits": 0,
                "evaluated": 0,
            }
        g = by_date[date_key]
        g["matches"].append(row)
        g["evaluated"] += 1
        g["primary_hits"] += 1 if row["primary_hit"] else 0
        g["triple_hits"] += 1 if row["triple_hit"] else 0
        md = row.get("matchday")
        if md is not None:
            g["matchdays"].add(md)

    sorted_dates = sorted(by_date.keys(), reverse=True)
    if days > 0:
        sorted_dates = sorted_dates[:days]

    day_list: list[dict] = []
    for date_key in sorted(sorted_dates):
        g = by_date[date_key]
        ev = g["evaluated"] or 1
        matchdays = sorted(g["matchdays"])
        day_list.append({
            "date": date_key,
            "matchday": matchdays[0] if len(matchdays) == 1 else None,
            "matchdays": matchdays,
            "evaluated": g["evaluated"],
            "primary_hits": g["primary_hits"],
            "triple_hits": g["triple_hits"],
            "primary_hit_rate": _rate(g["primary_hits"], g["evaluated"]),
            "triple_hit_rate": _rate(g["triple_hits"], g["evaluated"]),
            "matches": g["matches"],
        })

    today_str = china_today().isoformat()
    today = next((d for d in day_list if d["date"] == today_str), None)
    latest_day = day_list[-1] if day_list else None

    total_eval = sum(d["evaluated"] for d in day_list)
    total_primary = sum(d["primary_hits"] for d in day_list)
    total_triple = sum(d["triple_hits"] for d in day_list)

    cutoff = (china_today() - timedelta(days=6)).isoformat()
    rolling = [d for d in day_list if d["date"] >= cutoff]
    roll_eval = sum(d["evaluated"] for d in rolling)
    roll_primary = sum(d["primary_hits"] for d in rolling)
    roll_triple = sum(d["triple_hits"] for d in rolling)

    return {
        "days": day_list,
        "today": today,
        "latest_day": latest_day,
        "summary": {
            "days_with_matches": len(day_list),
            "total_evaluated": total_eval,
            "primary_hits": total_primary,
            "triple_hits": total_triple,
            "primary_hit_rate": _rate(total_primary, total_eval),
            "triple_hit_rate": _rate(total_triple, total_eval),
            "rolling_7d_evaluated": roll_eval,
            "rolling_7d_primary_hit_rate": _rate(roll_primary, roll_eval),
            "rolling_7d_triple_hit_rate": _rate(roll_triple, roll_eval),
        },
    }


def daily_report_cache_key(competition_slug: str, days: int) -> str:
    return f"{DAILY_REPORT_CACHE_PREFIX}{competition_slug}:{days}"


async def invalidate_daily_report_cache(competition_slug: str = "worldcup-2026") -> None:
    for days in (7, 14, 30):
        await cache_delete(daily_report_cache_key(competition_slug, days))


async def compute_daily_score_report(
    db: AsyncSession,
    competition_slug: str = "worldcup-2026",
    *,
    days: int = 14,
) -> dict:
    """Post-match daily backtest report grouped by Beijing date."""
    evaluated, skipped, skip_reasons = await _collect_evaluated_rows(db, competition_slug)
    daily = build_daily_report(evaluated, days=days)
    return {
        "competition_slug": competition_slug,
        "matches_evaluated": len(evaluated),
        "matches_skipped": skipped,
        "skip_reasons": skip_reasons,
        **daily,
        "notes": NOTES,
        "disclaimer": DISCLAIMER,
        "model_version": "crs-anchored-v2",
        "computed_at": datetime.now().isoformat(timespec="seconds"),
    }


async def get_or_compute_daily_report(
    db: AsyncSession,
    competition_slug: str = "worldcup-2026",
    *,
    days: int = 14,
    force: bool = False,
) -> dict:
    key = daily_report_cache_key(competition_slug, days)
    if not force:
        cached = await cache_get(key)
        if cached:
            return cached
    data = await compute_daily_score_report(db, competition_slug, days=days)
    await cache_set(key, data, ttl=DAILY_REPORT_CACHE_TTL)
    return data


async def compute_score_backtest(
    db: AsyncSession,
    competition_slug: str = "worldcup-2026",
) -> dict:
    """Backtest score picks on all finished matches with CRS odds."""
    evaluated, skipped, skip_reasons = await _collect_evaluated_rows(db, competition_slug)

    primary_hits = sum(1 for r in evaluated if r["primary_hit"])
    triple_hits = sum(1 for r in evaluated if r["triple_hit"])
    n = len(evaluated)

    groups: dict[str, dict] = {}
    prefer_date = competition_slug == "worldcup-2026"
    for row in evaluated:
        key, label = _backtest_group_key_label(row, prefer_date=prefer_date)
        md = row.get("matchday")
        if key not in groups:
            groups[key] = {
                "group_key": key,
                "label": label,
                "matchday": md,
                "matches": [],
                "primary_hits": 0,
                "triple_hits": 0,
                "evaluated": 0,
            }
        g = groups[key]
        g["matches"].append(row)
        g["evaluated"] += 1
        g["primary_hits"] += 1 if row["primary_hit"] else 0
        g["triple_hits"] += 1 if row["triple_hit"] else 0

    group_list = []
    for g in groups.values():
        ev = g["evaluated"] or 1
        g["primary_hit_rate"] = round(g["primary_hits"] / ev * 100, 1)
        g["triple_hit_rate"] = round(g["triple_hits"] / ev * 100, 1)
        group_list.append(g)
    if prefer_date:
        group_list.sort(key=lambda x: x["label"])
    else:
        group_list.sort(key=lambda x: (x.get("matchday") or 99, x["label"]))

    return {
        "competition_slug": competition_slug,
        "matches_evaluated": n,
        "matches_skipped": skipped,
        "skip_reasons": skip_reasons,
        "primary_hits": primary_hits,
        "triple_hits": triple_hits,
        "primary_hit_rate": round(primary_hits / n * 100, 1) if n else 0.0,
        "triple_hit_rate": round(triple_hits / n * 100, 1) if n else 0.0,
        "groups": group_list,
        "notes": NOTES,
        "disclaimer": DISCLAIMER,
        "model_version": "crs-anchored-v2",
        "computed_at": datetime.now().isoformat(timespec="seconds"),
    }
