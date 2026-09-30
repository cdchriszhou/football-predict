#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键重算五大联赛未赛比分预测（强制跳过缓存，默认 rule_engine）。

Usage (from backend/):
  ./venv/Scripts/python scripts/repredict_big_five_upcoming.py --dry-run
  ./venv/Scripts/python scripts/repredict_big_five_upcoming.py
  ./venv/Scripts/python scripts/repredict_big_five_upcoming.py --all
  ./venv/Scripts/python scripts/repredict_big_five_upcoming.py --slug premier-league --limit 20
  ./venv/Scripts/python scripts/repredict_big_five_upcoming.py --skip-odds --model rule_engine
  ./venv/Scripts/python scripts/repredict_big_five_upcoming.py --days 7

说明:
  - 默认重算未来 21 天内未赛；`--all` 重算全部未赛（可能上千场）。
  - 默认先跑赔率爬虫（体彩 + Odds API，若已配置 Key），再对目标场次 skip_cache 重算。
  - SQLite 下默认 model=rule_engine，避免 LLM 串行卡死；可用 --model deepseek 覆盖。
  - 历史已完赛场次不重算（结果已定，且旧预测保留作复盘）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import or_, select

from data.competitions import COMPETITIONS
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values
from db import async_session
from db.models import Match, Odds, Prediction
from db.redis_client import cache_delete
from db.sqlite_write import IS_SQLITE, commit_session
from service.prediction_service import PredictionService
from utils.logger import logger

BIG_FIVE = [
    slug
    for slug, comp in COMPETITIONS.items()
    if comp.get("type") == "club" and slug in {
        "premier-league", "la-liga", "serie-a", "bundesliga", "ligue-1",
    }
]


def _parse_best(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return [raw] if ":" in str(raw) else []
    if isinstance(data, dict):
        scores = list(data.get("scores") or [])
        if data.get("upset"):
            scores.append(data["upset"])
        return [s for s in scores if s]
    if isinstance(data, list):
        return [s for s in data if s]
    return []


async def _crawl_odds(slugs: list[str]) -> dict:
    from crawler.odds_crawler import run_odds_crawler
    from crawler.sporttery_client import fetch_sporttery_on_sale

    pool = await fetch_sporttery_on_sale()
    out: dict = {}
    async with async_session() as db:
        for slug in slugs:
            try:
                out[slug] = await run_odds_crawler(db, slug, sporttery_pool=pool)
                await commit_session(db)
            except Exception as exc:
                out[slug] = {"status": "failed", "error": str(exc)}
                logger.warning("odds crawl failed for %s: %s", slug, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass
    return out


async def _load_targets(
    db,
    slugs: list[str],
    *,
    days: int | None,
    limit: int | None,
    include_live: bool,
) -> list[Match]:
    statuses = match_status_in_db_values(MATCH_UPCOMING)
    if include_live:
        statuses = match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)

    q = (
        select(Match)
        .where(
            Match.competition_slug.in_(slugs),
            Match.status.in_(statuses),
            Match.result_a.is_(None),
            Match.result_b.is_(None),
        )
        .order_by(Match.match_time.asc(), Match.id.asc())
    )
    if days is not None and days >= 0:
        # match_time stored naive local-ish; compare as naive UTC-ish cutoff.
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)
        # Also keep rows with null match_time
        q = q.where(or_(Match.match_time.is_(None), Match.match_time <= cutoff))

    rows = (await db.execute(q)).scalars().all()
    if limit is not None and limit > 0:
        rows = rows[:limit]
    return list(rows)


async def _clear_prediction_cache(match_id: int) -> None:
    for suffix in ("auto", "rule_engine", "deepseek", "qwen", "glm"):
        try:
            await cache_delete(f"prediction:{match_id}:{suffix}")
        except Exception:
            pass


async def run(
    *,
    slugs: list[str],
    model: str,
    dry_run: bool,
    skip_odds: bool,
    days: int | None,
    limit: int | None,
    include_live: bool,
) -> int:
    print(
        f"slugs={slugs} model={model} dry_run={dry_run} skip_odds={skip_odds} "
        f"days={days} limit={limit} include_live={include_live}",
        flush=True,
    )

    odds_summary = {}
    if not dry_run and not skip_odds:
        print("==> crawling odds ...", flush=True)
        odds_summary = await _crawl_odds(slugs)
        for slug, info in odds_summary.items():
            if not isinstance(info, dict):
                continue
            print(
                f"  [{slug}] status={info.get('status')} "
                f"+{info.get('created', 0)} ~{info.get('updated', 0)} "
                f"skip={info.get('skipped', 0)} "
                f"sporttery={info.get('sporttery_matched', 0)} "
                f"odds_api={info.get('odds_api_matched', 0)}",
                flush=True,
            )
    elif skip_odds:
        import os
        os.environ["SKIP_MATCH_ODDS_REFRESH"] = "1"
        print("==> skip odds crawl + per-match odds refresh", flush=True)

    async with async_session() as db:
        targets = await _load_targets(
            db, slugs, days=days, limit=limit, include_live=include_live,
        )
        # Prefetch old predictions for change summary
        old_by_id: dict[int, str | None] = {}
        if targets:
            ids = [m.id for m in targets]
            preds = (
                await db.execute(select(Prediction).where(Prediction.match_id.in_(ids)))
            ).scalars().all()
            for p in preds:
                old_by_id[p.match_id] = p.best_score

        odds_cov = 0
        if targets:
            oids = (
                await db.execute(
                    select(Odds.match_id).where(
                        Odds.match_id.in_([m.id for m in targets]),
                        Odds.win_win.isnot(None),
                    )
                )
            ).scalars().all()
            odds_cov = len(set(oids))

        print(
            f"==> targets={len(targets)} with_euro_odds={odds_cov}",
            flush=True,
        )
        for m in targets[:15]:
            print(
                f"  preview {m.competition_slug} #{m.id} {m.match_time} "
                f"{m.team_a} vs {m.team_b} old={_parse_best(old_by_id.get(m.id))}",
                flush=True,
            )
        if len(targets) > 15:
            print(f"  ... and {len(targets) - 15} more", flush=True)

        if dry_run:
            print("dry-run: no predictions written", flush=True)
            return 0

        if not targets:
            print("nothing to repredict", flush=True)
            return 0

        # Default model safety on SQLite
        use_model = model
        if IS_SQLITE and use_model in (None, "", "auto"):
            use_model = "rule_engine"
            print("SQLite detected: using model=rule_engine", flush=True)

        service = PredictionService()
        ok = failed = changed = 0
        failures: list[str] = []

        for idx, match in enumerate(targets, start=1):
            label = f"{match.team_a} vs {match.team_b}"
            print(f"[{idx}/{len(targets)}] {match.competition_slug} {label} ...", flush=True)
            try:
                await _clear_prediction_cache(match.id)
                result = await asyncio.wait_for(
                    service.predict_match(
                        match.id, db, model=use_model, skip_cache=True,
                    ),
                    timeout=90.0,
                )
                if not result:
                    failed += 1
                    failures.append(f"{match.id}:{label}:empty")
                    continue
                ok += 1
                new_scores = result.get("best_scores") or []
                upset = result.get("upset_score")
                new_line = list(new_scores) + ([upset] if upset else [])
                old_line = _parse_best(old_by_id.get(match.id))
                if [str(x) for x in new_line] != [str(x) for x in old_line]:
                    changed += 1
                print(
                    f"  -> WDL {result.get('win_rate'):.1f}/"
                    f"{result.get('draw_rate'):.1f}/{result.get('lose_rate'):.1f} "
                    f"scores={new_scores} upset={upset} "
                    f"book={bool((result.get('odds_sources') or []))}",
                    flush=True,
                )
            except Exception as exc:
                failed += 1
                failures.append(f"{match.id}:{label}:{exc}")
                logger.exception("repredict failed match %s", match.id)
                try:
                    await db.rollback()
                except Exception:
                    pass

        print(
            f"==> done ok={ok} failed={failed} changed={changed} total={len(targets)}",
            flush=True,
        )
        if failures:
            print("failures:", flush=True)
            for f in failures[:20]:
                print(f"  {f}", flush=True)
        return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="重算五大联赛未赛比分预测")
    parser.add_argument(
        "--slug",
        action="append",
        dest="slugs",
        help="只跑指定联赛（可重复）；默认五大联赛全部",
    )
    parser.add_argument(
        "--model",
        default="rule_engine",
        help="预测模型：rule_engine（默认）/ auto / deepseek / qwen / glm",
    )
    parser.add_argument("--dry-run", action="store_true", help="只列出目标，不写库")
    parser.add_argument("--skip-odds", action="store_true", help="跳过赔率爬虫")
    parser.add_argument(
        "--days",
        type=int,
        default=21,
        help="只重算未来 N 天内的未赛（默认 21；与 --all 互斥）",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="重算全部未赛（忽略 --days）",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 场")
    parser.add_argument(
        "--include-live",
        action="store_true",
        help="同时重算进行中的比赛",
    )
    args = parser.parse_args()

    slugs = args.slugs or list(BIG_FIVE)
    bad = [s for s in slugs if s not in BIG_FIVE]
    if bad:
        print(f"unsupported slug(s) for this script: {bad}; allowed={BIG_FIVE}")
        return 1

    days = None if args.all else args.days
    return asyncio.run(
        run(
            slugs=slugs,
            model=args.model,
            dry_run=args.dry_run,
            skip_odds=args.skip_odds,
            days=days,
            limit=args.limit,
            include_live=args.include_live,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
