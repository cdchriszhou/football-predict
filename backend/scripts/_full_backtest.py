# -*- coding: utf-8 -*-
import asyncio, os, sys
from pathlib import Path
from collections import defaultdict
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from sqlalchemy import select
from db import async_session
from db.models import Match, Odds, Prediction
from data.knockout_advance import display_teams_for_match, load_knockout_slot_index_cached
from service.score_backtest import (
    _best_odds_with_crs, _evaluate_match, _find_history_for_match,
    _picks_from_db_prediction, _resolve_backtest_kickoff, _wdl_from_european,
)
from utils.score_prediction import actual_score_for_match

async def main():
    async with async_session() as db:
        ko_index = await load_knockout_slot_index_cached(db, "worldcup-2026")
        rows = (await db.execute(select(Match).where(
            Match.competition_slug == "worldcup-2026",
            Match.result_a.isnot(None), Match.result_b.isnot(None),
        ))).scalars().all()
        sp=st=rp=rt=n=0
        by_stage=defaultdict(lambda:{"n":0,"sp":0,"st":0,"rp":0,"rt":0})
        for match in rows:
            ta,tb=display_teams_for_match(match,ko_index)
            ta,tb=ta or match.team_a,tb or match.team_b
            hist=_find_history_for_match(ta,tb,stage=match.stage or "",match_time=match.match_time)
            actual=actual_score_for_match(result_a=int(match.result_a),result_b=int(match.result_b),team_a=ta,team_b=tb,hist=hist)
            all_odds=(await db.execute(select(Odds).where(Odds.match_id==match.id).order_by(Odds.id.desc()))).scalars().all()
            odds_row,crs=_best_odds_with_crs(list(all_odds))
            pred_row=(await db.execute(select(Prediction).where(Prediction.match_id==match.id).order_by(Prediction.create_time.desc()).limit(1))).scalar_one_or_none()
            if not crs and hist: crs={str(k):float(v) for k,v in (hist.get("score_odds") or {}).items()}
            odds_meta=None
            if odds_row: odds_meta={"win_win":odds_row.win_win,"draw":odds_row.draw,"win_lose":odds_row.win_lose,"handicap":odds_row.handicap}
            wdl=(pred_row.win_rate,pred_row.draw_rate,pred_row.lose_rate) if pred_row else None
            if not wdl and hist: wdl=_wdl_from_european(hist.get("european")) or (50.,25.,25.)
            kickoff=_resolve_backtest_kickoff(ta,tb,match.match_time,hist)
            pub=_picks_from_db_prediction(pred_row)
            sr=_evaluate_match(team_a=ta,team_b=tb,actual=actual,crs=crs or {},wdl=wdl,odds_meta=odds_meta,match_time=kickoff,stage=match.stage or "",published_picks=pub)
            rr=_evaluate_match(team_a=ta,team_b=tb,actual=actual,crs=crs or {},wdl=wdl,odds_meta=odds_meta,match_time=kickoff,stage=match.stage or "",published_picks=None)
            if not sr or not rr: continue
            n+=1; sp+=sr["primary_hit"]; st+=sr["triple_hit"]; rp+=rr["primary_hit"]; rt+=rr["triple_hit"]
            g=by_stage[match.stage or "小组赛"]; g["n"]+=1; g["sp"]+=sr["primary_hit"]; g["st"]+=sr["triple_hit"]; g["rp"]+=rr["primary_hit"]; g["rt"]+=rr["triple_hit"]
        print(f"ALL FINISHED n={n}")
        print(f"stored primary={sp/n*100:.1f}% triple={st/n*100:.1f}%")
        print(f"replay primary={rp/n*100:.1f}% triple={rt/n*100:.1f}%")
        for stg,g in sorted(by_stage.items()):
            t=g["n"]
            print(f"  {stg}: n={t} stored {g['sp']/t*100:.0f}/{g['st']/t*100:.0f}% replay {g['rp']/t*100:.0f}/{g['rt']/t*100:.0f}%")

if __name__=="__main__":
    asyncio.run(main())
