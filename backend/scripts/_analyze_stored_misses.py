"""Analyze stored prediction misses only."""
import asyncio
import json
from collections import Counter, defaultdict

from sqlalchemy import select

from db import async_session
from db.models import Match, Prediction
from service.score_backtest import _evaluate_match, _picks_from_db_prediction
from service.score_pick import score_matches_pick
from data.knockout_advance import display_teams_for_match, load_knockout_slot_index_cached
from service.score_backtest import (
    _best_odds_with_crs,
    _find_history_for_match,
    _odds_meta_from_history,
    _resolve_backtest_kickoff,
    _wdl_from_european,
)
from db.models import Odds


async def main():
    async with async_session() as db:
        ko_index = await load_knockout_slot_index_cached(db, "worldcup-2026")
        matches = (
            await db.execute(
                select(Match).where(
                    Match.competition_slug == "worldcup-2026",
                    Match.result_a.isnot(None),
                    Match.result_b.isnot(None),
                )
            )
        ).scalars().all()

        triple_miss = []
        primary_miss_draw = []
        primary_miss_blowout = []

        for match in matches:
            pred = (
                await db.execute(
                    select(Prediction)
                    .where(Prediction.match_id == match.id)
                    .order_by(Prediction.create_time.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            published = _picks_from_db_prediction(pred)
            if not published:
                continue
            p1, p2, upset, all_picks = published
            actual = f"{match.result_a}:{match.result_b}"
            ta, tb = display_teams_for_match(match, ko_index)
            ta, tb = ta or match.team_a, tb or match.team_b

            all_odds = (
                await db.execute(
                    select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc())
                )
            ).scalars().all()
            _, crs = _best_odds_with_crs(list(all_odds))
            hist = _find_history_for_match(ta, tb, stage=match.stage or "", match_time=match.match_time)
            if not crs and hist:
                crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            eval_crs = crs or {"1:0": 10.0}

            triple = any(score_matches_pick(actual, p, eval_crs) for p in all_picks if p)
            primary = score_matches_pick(actual, p1, eval_crs)
            if not triple:
                triple_miss.append(
                    {
                        "match": f"{ta} vs {tb}",
                        "actual": actual,
                        "picks": all_picks,
                        "stage": match.stage,
                        "has_crs": bool(crs),
                        "reason": (pred.reason or "")[:120] if pred else "",
                    }
                )
            if not primary:
                def outcome(s):
                    a, b = map(int, s.split(":"))
                    if a > b:
                        return "win"
                    if a < b:
                        return "lose"
                    return "draw"

                ao = outcome(actual)
                po = outcome(p1)
                if ao == "draw" and po != "draw":
                    primary_miss_draw.append(f"{ta} vs {tb} actual={actual} pick={p1}")
                total = match.result_a + match.result_b
                if total >= 5 and po != ao:
                    primary_miss_blowout.append(f"{ta} vs {tb} actual={actual} pick={p1}")

        print(f"triple_miss={len(triple_miss)}")
        print("by stage:", Counter(m["stage"] or "小组赛" for m in triple_miss))
        print("by has_crs:", Counter(m["has_crs"] for m in triple_miss))
        print("\n=== TRIPLE MISS DETAIL ===")
        for m in triple_miss:
            print(m)

        print(f"\nprimary miss draw actual: {len(primary_miss_draw)}")
        for x in primary_miss_draw[:8]:
            print(" ", x)
        print(f"primary miss high-scoring (5+ goals): {len(primary_miss_blowout)}")


if __name__ == "__main__":
    asyncio.run(main())
