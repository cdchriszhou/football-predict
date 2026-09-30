# -*- coding: utf-8 -*-
"""Detailed knockout backtest with CRS source tracking."""
from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from sqlalchemy import select

from data.knockout_advance import display_teams_for_match, load_knockout_slot_index_cached
from db import async_session
from db.models import Match, Odds, Prediction
from service.score_backtest import (
    _best_odds_with_crs,
    _evaluate_match,
    _find_history_for_match,
    _picks_from_db_prediction,
    _resolve_backtest_kickoff,
    _wdl_from_european,
)
from utils.score_prediction import actual_score_for_match

STAGES = ("1/8决赛", "1/4决赛", "半决赛")


async def main():
    async with async_session() as db:
        ko_index = await load_knockout_slot_index_cached(db, "worldcup-2026")
        rows = (
            await db.execute(
                select(Match).where(
                    Match.competition_slug == "worldcup-2026",
                    Match.stage.in_(STAGES),
                    Match.result_a.isnot(None),
                ).order_by(Match.match_time)
            )
        ).scalars().all()

        totals = defaultdict(lambda: {"n": 0, "sp": 0, "st": 0, "rp": 0, "rt": 0})
        print(f"{'Match':<28} {'Actual':<6} {'CRS':<5} {'Stored':<22} {'Replay':<22} S/T R/T")
        print("-" * 95)
        for match in rows:
            ta, tb = display_teams_for_match(match, ko_index)
            ta, tb = ta or match.team_a, tb or match.team_b
            hist = _find_history_for_match(ta, tb, stage=match.stage or "", match_time=match.match_time)
            actual = actual_score_for_match(
                result_a=int(match.result_a), result_b=int(match.result_b),
                team_a=ta, team_b=tb, hist=hist,
            )
            all_odds = (await db.execute(
                select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc())
            )).scalars().all()
            odds_row, crs = _best_odds_with_crs(list(all_odds))
            pred_row = (await db.execute(
                select(Prediction).where(Prediction.match_id == match.id)
                .order_by(Prediction.create_time.desc()).limit(1)
            )).scalar_one_or_none()
            if not crs and hist:
                crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            odds_meta = None
            if odds_row:
                odds_meta = {
                    "win_win": odds_row.win_win, "draw": odds_row.draw,
                    "win_lose": odds_row.win_lose, "handicap": odds_row.handicap,
                }
            wdl = (pred_row.win_rate, pred_row.draw_rate, pred_row.lose_rate) if pred_row else None
            if not wdl and hist:
                wdl = _wdl_from_european(hist.get("european")) or (50.0, 25.0, 25.0)
            kickoff = _resolve_backtest_kickoff(ta, tb, match.match_time, hist)
            published = _picks_from_db_prediction(pred_row)

            stored = _evaluate_match(
                team_a=ta, team_b=tb, actual=actual, crs=crs or {}, wdl=wdl,
                odds_meta=odds_meta, match_time=kickoff, stage=match.stage or "",
                published_picks=published,
            )
            replay = _evaluate_match(
                team_a=ta, team_b=tb, actual=actual, crs=crs or {}, wdl=wdl,
                odds_meta=odds_meta, match_time=kickoff, stage=match.stage or "",
                published_picks=None,
            )
            if not stored or not replay:
                print(f"{ta} vs {tb:<12} {actual:<6} {'NO':<5} SKIP (no CRS synth)")
                continue
            stg = match.stage or "?"
            g = totals[stg]
            g["n"] += 1
            g["sp"] += stored["primary_hit"]
            g["st"] += stored["triple_hit"]
            g["rp"] += replay["primary_hit"]
            g["rt"] += replay["triple_hit"]
            crs_tag = stored["crs_source"][:4]
            s_pri = stored["primary_pick"]
            r_pri = replay["primary_pick"]
            sh = "Y" if stored["primary_hit"] else "N"
            rh = "Y" if replay["primary_hit"] else "N"
            st = "Y" if stored["triple_hit"] else "N"
            rt = "Y" if replay["triple_hit"] else "N"
            wdl_s = f"({pred_row.draw_rate:.0f}%D)" if pred_row else ""
            print(
                f"{ta} vs {tb:<12} {actual:<6} {crs_tag:<5} "
                f"{s_pri+'/'+stored['secondary_pick']:<22} {r_pri+'/'+replay['secondary_pick']:<22} "
                f"{sh}/{st} {rh}/{rt} {wdl_s} src={stored['pick_source']}"
            )

        print("\n=== SUMMARY ===")
        for stg, g in sorted(totals.items()):
            if g["n"]:
                n = g["n"]
                print(
                    f"{stg}: n={n} stored_pri={g['sp']/n*100:.0f}% triple={g['st']/n*100:.0f}% "
                    f"replay_pri={g['rp']/n*100:.0f}% triple={g['rt']/n*100:.0f}%"
                )


if __name__ == "__main__":
    asyncio.run(main())
