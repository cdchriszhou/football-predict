"""Compare stored vs replay picks on finished matches."""
import asyncio
from collections import defaultdict

from sqlalchemy import select

from db import async_session
from db.models import Match, Odds, Prediction
from service.score_backtest import (
    _best_odds_with_crs,
    _evaluate_match,
    _find_history_for_match,
    _odds_meta_from_history,
    _picks_from_db_prediction,
    _resolve_backtest_kickoff,
    _wdl_from_european,
)
from data.knockout_advance import display_teams_for_match, load_knockout_slot_index_cached


async def main():
    async with async_session() as db:
        ko_index = await load_knockout_slot_index_cached(db, "worldcup-2026")
        rows = (
            await db.execute(
                select(Match).where(
                    Match.competition_slug == "worldcup-2026",
                    Match.result_a.isnot(None),
                    Match.result_b.isnot(None),
                )
            )
        ).scalars().all()

        stored_p, stored_t, replay_p, replay_t, n = 0, 0, 0, 0, 0
        improved, regressed = 0, 0
        by_stage = defaultdict(lambda: {"n": 0, "sp": 0, "st": 0, "rp": 0, "rt": 0})

        for match in rows:
            ta, tb = display_teams_for_match(match, ko_index)
            ta, tb = ta or match.team_a, tb or match.team_b
            hist = _find_history_for_match(
                ta, tb, stage=match.stage or "", match_time=match.match_time
            )
            from utils.score_prediction import actual_score_for_match
            actual = actual_score_for_match(
                result_a=int(match.result_a),
                result_b=int(match.result_b),
                team_a=ta,
                team_b=tb,
                hist=hist,
            )
            all_odds = (
                await db.execute(
                    select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc())
                )
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
            if not wdl and hist:
                wdl = _wdl_from_european(hist.get("european")) or (50.0, 25.0, 25.0)
            kickoff = _resolve_backtest_kickoff(ta, tb, match.match_time, hist)
            published = _picks_from_db_prediction(pred_row)

            stored_row = _evaluate_match(
                team_a=ta,
                team_b=tb,
                actual=actual,
                crs=crs or {},
                wdl=wdl,
                odds_meta=odds_meta,
                match_time=kickoff,
                stage=match.stage or "",
                published_picks=published,
            )
            replay_row = _evaluate_match(
                team_a=ta,
                team_b=tb,
                actual=actual,
                crs=crs or {},
                wdl=wdl,
                odds_meta=odds_meta,
                match_time=kickoff,
                stage=match.stage or "",
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
            stg = match.stage or "小组赛"
            g = by_stage[stg]
            g["n"] += 1
            g["sp"] += sp
            g["st"] += st
            g["rp"] += rp
            g["rt"] += rt
            if rt and not st:
                improved += 1
            if st and not rt:
                regressed += 1

        print(f"n={n}")
        print(f"stored primary={stored_p/n*100:.1f}% triple={stored_t/n*100:.1f}%")
        print(f"replay primary={replay_p/n*100:.1f}% triple={replay_t/n*100:.1f}%")
        print(f"triple improved={improved} regressed={regressed}")
        for stg, g in sorted(by_stage.items()):
            t = g["n"]
            print(
                f"  {stg}: n={t} "
                f"stored {g['sp']/t*100:.0f}/{g['st']/t*100:.0f}% "
                f"replay {g['rp']/t*100:.0f}/{g['rt']/t*100:.0f}%"
            )


if __name__ == "__main__":
    asyncio.run(main())
