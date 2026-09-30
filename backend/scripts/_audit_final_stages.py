# -*- coding: utf-8 -*-
"""Temporary audit: late-stage matches, predictions, stored vs replay."""
from __future__ import annotations

import asyncio
import json
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
from service.score_pick_config import get_config, load_config
from utils.score_prediction import actual_score_for_match


LATE_STAGES = ("1/8决赛", "1/4决赛", "半决赛", "季军赛", "决赛")


async def main() -> None:
    cfg = get_config()
    print("=== CONFIG ===")
    print(f"PIPELINE_USE_NEW_ENSEMBLE={cfg.get('PIPELINE_USE_NEW_ENSEMBLE')}")
    print(f"STAGE_DRAW_BOOST_KO={cfg.get('STAGE_DRAW_BOOST_KO')}")
    print(f"KO_ROUND_PARAMS 半决赛={cfg.get('KO_ROUND_PARAMS', {}).get('半决赛')}")

    async with async_session() as db:
        ko_index = await load_knockout_slot_index_cached(db, "worldcup-2026")

        print("\n=== LATE STAGE MATCHES ===")
        for stage in LATE_STAGES:
            rows = (
                await db.execute(
                    select(Match)
                    .where(Match.competition_slug == "worldcup-2026", Match.stage == stage)
                    .order_by(Match.match_time)
                )
            ).scalars().all()
            print(f"\n--- {stage} ({len(rows)}) ---")
            for m in rows:
                ta, tb = display_teams_for_match(m, ko_index)
                ta, tb = ta or m.team_a, tb or m.team_b
                pred = (
                    await db.execute(
                        select(Prediction)
                        .where(Prediction.match_id == m.id)
                        .order_by(Prediction.create_time.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                picks = _picks_from_db_prediction(pred) if pred else None
                print(
                    f"  id={m.id} {ta} vs {tb} | {m.result_a}:{m.result_b} "
                    f"pen={m.penalty_a}:{m.penalty_b} status={m.status} | "
                    f"stored={picks} wdl=({pred.win_rate if pred else None},"
                    f"{pred.draw_rate if pred else None},{pred.lose_rate if pred else None})"
                )

        print("\n=== BACKTEST: stored vs replay (late stages only) ===")
        rows = (
            await db.execute(
                select(Match).where(
                    Match.competition_slug == "worldcup-2026",
                    Match.stage.in_(LATE_STAGES),
                    Match.result_a.isnot(None),
                    Match.result_b.isnot(None),
                )
            )
        ).scalars().all()

        stored_p = stored_t = replay_p = replay_t = n = 0
        by_stage = defaultdict(lambda: {"n": 0, "sp": 0, "st": 0, "rp": 0, "rt": 0, "details": []})

        for match in rows:
            ta, tb = display_teams_for_match(match, ko_index)
            ta, tb = ta or match.team_a, tb or match.team_b
            hist = _find_history_for_match(ta, tb, stage=match.stage or "", match_time=match.match_time)
            actual = actual_score_for_match(
                result_a=int(match.result_a),
                result_b=int(match.result_b),
                team_a=ta,
                team_b=tb,
                hist=hist,
            )
            all_odds = (
                await db.execute(select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc()))
            ).scalars().all()
            odds_row, crs = _best_odds_with_crs(list(all_odds))
            pred_row = (
                await db.execute(
                    select(Prediction)
                    .where(Prediction.match_id == match.id)
                    .order_by(Prediction.create_time.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not crs and hist:
                crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            odds_meta = None
            if odds_row:
                odds_meta = {
                    "win_win": odds_row.win_win,
                    "draw": odds_row.draw,
                    "win_lose": odds_row.win_lose,
                    "handicap": odds_row.handicap,
                }
            wdl = None
            if pred_row:
                wdl = (pred_row.win_rate, pred_row.draw_rate, pred_row.lose_rate)
            if not wdl and hist:
                wdl = _wdl_from_european(hist.get("european")) or (50.0, 25.0, 25.0)
            kickoff = _resolve_backtest_kickoff(ta, tb, match.match_time, hist)
            published = _picks_from_db_prediction(pred_row)

            stored_row = _evaluate_match(
                team_a=ta, team_b=tb, actual=actual, crs=crs or {}, wdl=wdl,
                odds_meta=odds_meta, match_time=kickoff, stage=match.stage or "",
                published_picks=published,
            )
            replay_row = _evaluate_match(
                team_a=ta, team_b=tb, actual=actual, crs=crs or {}, wdl=wdl,
                odds_meta=odds_meta, match_time=kickoff, stage=match.stage or "",
                published_picks=None,
            )
            if not stored_row or not replay_row:
                continue
            n += 1
            sp, st = stored_row["primary_hit"], stored_row["triple_hit"]
            rp, rt = replay_row["primary_hit"], replay_row["triple_hit"]
            stored_p += sp
            stored_t += st
            replay_p += rp
            replay_t += rt
            stg = match.stage or "?"
            g = by_stage[stg]
            g["n"] += 1
            g["sp"] += sp
            g["st"] += st
            g["rp"] += rp
            g["rt"] += rt
            g["details"].append({
                "match": f"{ta} vs {tb}",
                "actual": actual,
                "stored": stored_row.get("picks"),
                "replay": replay_row.get("picks"),
                "crs_top3": stored_row.get("crs_top3"),
                "stored_pri_hit": sp,
                "replay_pri_hit": rp,
                "stored_triple_hit": st,
                "replay_triple_hit": rt,
                "has_crs": bool(crs),
            })

        if n:
            print(f"n={n}")
            print(f"stored primary={stored_p/n*100:.1f}% triple={stored_t/n*100:.1f}%")
            print(f"replay primary={replay_p/n*100:.1f}% triple={replay_t/n*100:.1f}%")
            for stg, g in sorted(by_stage.items()):
                t = g["n"]
                print(
                    f"  {stg}: n={t} stored {g['sp']/t*100:.0f}/{g['st']/t*100:.0f}% "
                    f"replay {g['rp']/t*100:.0f}/{g['rt']/t*100:.0f}%"
                )
                for d in g["details"]:
                    print(f"    {d['match']} actual={d['actual']} crs={d['has_crs']}")
                    print(f"      stored={d['stored']} hit_pri={d['stored_pri_hit']} hit_tri={d['stored_triple_hit']}")
                    print(f"      replay={d['replay']} hit_pri={d['replay_pri_hit']} hit_tri={d['replay_triple_hit']}")
        else:
            print("No finished late-stage matches with predictions.")


if __name__ == "__main__":
    asyncio.run(main())
