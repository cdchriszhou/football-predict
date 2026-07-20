# -*- coding: utf-8 -*-
"""Diagnose 2026-06-21 four-match prediction misses."""
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from db import async_session
from db.models import Match, Prediction, Odds, Team
from service.score_backtest import run_score_prediction, score_matches_pick
from service.score_pick import run_full_score_pipeline

ACTUAL = {
    ("荷兰", "瑞典"): "5:1",
    ("德国", "科特迪瓦"): "2:1",
    ("库拉索", "厄瓜多尔"): "0:0",
    ("日本", "突尼斯"): "4:0",
}


def wdl_outcome(score: str, *, home_perspective: bool = True) -> str:
    a, b = map(int, score.split(":"))
    if a > b:
        return "主胜"
    if a < b:
        return "客胜"
    return "平"


async def main():
    data = json.loads(Path("scripts/_today4.json").read_text(encoding="utf-8"))
    async with async_session() as db:
        for row in data:
            ta, tb = row["a"], row["b"]
            actual = ACTUAL.get((ta, tb))
            if not actual:
                continue
            mid = row["id"]
            m = (await db.execute(select(Match).where(Match.id == mid))).scalar_one()
            pred = (await db.execute(
                select(Prediction).where(Prediction.match_id == mid)
                .order_by(Prediction.create_time.desc())
            )).scalars().first()
            odds = (await db.execute(
                select(Odds).where(Odds.match_id == mid).order_by(Odds.id.desc())
            )).scalars().first()
            ta_obj = (await db.execute(
                select(Team).where(Team.competition_slug == m.competition_slug, Team.name == ta)
            )).scalar_one_or_none()
            tb_obj = (await db.execute(
                select(Team).where(Team.competition_slug == m.competition_slug, Team.name == tb)
            )).scalar_one_or_none()
            fused = prepare_fused_odds(odds, ta, tb) if odds else {}
            crs = fused.get("score_odds") or {}
            wr, dr, lr = row["wdl"]
            wdl_fav = max([("主胜", wr), ("平", dr), ("客胜", lr)], key=lambda x: x[1])
            act_wdl = wdl_outcome(actual)
            norm = row["norm"]
            picks = (norm.get("best_scores") or []) + (
                [norm["upset_score"]] if norm.get("upset_score") else []
            )
            triple = any(score_matches_pick(actual, p, crs) for p in picks if p)
            print("=" * 60)
            print(f"{ta} vs {tb}  实际 {actual} ({act_wdl})")
            wdl_ok = wdl_fav[0] == act_wdl
            print(f"  W/D/L pred {wr:.0f}/{dr:.0f}/{lr:.0f}% -> {wdl_fav[0]}  ok={wdl_ok}")
            print(f"  比分推荐 {picks}  三选命中={triple}")
            print(f"  CRS keys={len(crs)}  SPF={row.get('spf')}")
            if crs:
                top = sorted(crs.items(), key=lambda x: x[1])[:6]
                print(f"  CRS top6: {top}")
            if pred and crs:
                odds_meta = {
                    "win_win": odds.win_win if odds else None,
                    "draw": odds.draw if odds else None,
                    "win_lose": odds.win_lose if odds else None,
                    "handicap": odds.handicap if odds else None,
                }
                wdl_t = (wr, dr, lr)
                p1, p2, upset, pipe = run_score_prediction(
                    ta, tb, crs, wdl_t, odds_meta, stage="小组赛",
                )
                print(f"  pipeline replay: {pipe} upset={upset}")
                ph = score_matches_pick(actual, p1, crs)
                th = any(score_matches_pick(actual, p, crs) for p in pipe if p)
                print(f"  replay primary={ph} triple={th}")


if __name__ == "__main__":
    asyncio.run(main())
