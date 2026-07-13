"""Measure triple-hit on stored misses after pipeline fixes."""
import asyncio

from sqlalchemy import select

from db import async_session
from db.models import Match, Odds, Prediction, Team
from service.prediction_service import prepare_fused_odds
from service.score_backtest import (
    _best_odds_with_crs,
    _find_history_for_match,
    _picks_from_db_prediction,
    score_matches_pick,
)
from service.score_pick import run_full_score_pipeline
from data.knockout_advance import display_teams_for_match, load_knockout_slot_index_cached
from service.calibration_service import CalibratedRuleEngine
from service.match_context import build_group_context
from service.prediction_service import infer_matchday, team_to_dict


async def main():
    engine = CalibratedRuleEngine()
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

        stored_triple_miss = 0
        replay_triple_miss = 0
        n = 0
        fixed = 0

        for match in matches:
            pred = (
                await db.execute(
                    select(Prediction)
                    .where(Prediction.match_id == match.id)
                    .order_by(Prediction.create_time.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not pred:
                continue
            published = _picks_from_db_prediction(pred)
            if not published:
                continue
            ta, tb = display_teams_for_match(match, ko_index)
            ta, tb = ta or match.team_a, tb or match.team_b
            hist = _find_history_for_match(ta, tb, stage=match.stage or "", match_time=match.match_time)
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
            if not crs and hist:
                crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            eval_crs = crs or {"1:0": 10.0}

            p1, p2, upset, stored_all = published
            stored_triple = any(score_matches_pick(actual, p, eval_crs) for p in stored_all if p)

            team_a = (
                await db.execute(
                    select(Team).where(Team.competition_slug == match.competition_slug, Team.name == match.team_a)
                )
            ).scalar_one_or_none()
            team_b = (
                await db.execute(
                    select(Team).where(Team.competition_slug == match.competition_slug, Team.name == match.team_b)
                )
            ).scalar_one_or_none()
            fused = prepare_fused_odds(odds_row, ta, tb) if odds_row else {}
            if not crs and hist:
                crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            score_odds = {k: v for k, v in (fused.get("score_odds") or crs or {}).items() if not str(k).startswith("_")}
            rule = engine.evaluate(
                team_to_dict(team_a) if team_a else {"name": ta, "rank": 50},
                team_to_dict(team_b) if team_b else {"name": tb, "rank": 50},
                odds=fused,
                h2h=[],
            )
            md = await infer_matchday(match, db)
            group_context = build_group_context(
                match.stage or "",
                group_name=match.group_name or "",
                matchday=md,
                team_a=ta,
                team_b=tb,
                rank_a=(team_a.rank if team_a else 50),
                rank_b=(team_b.rank if team_b else 50),
                location=match.location or "",
            )
            best, upset_r, all_picks, _ = run_full_score_pipeline(
                score_odds or crs or {},
                win_rate=pred.win_rate,
                draw_rate=pred.draw_rate,
                lose_rate=pred.lose_rate,
                expected_a=rule.expected_a,
                expected_b=rule.expected_b,
                model_scores=rule.best_scores,
                stage=match.stage,
                sp_win=fused.get("win_win"),
                sp_lose=fused.get("win_lose"),
                sp_draw=fused.get("draw"),
                handicap=fused.get("handicap"),
                rank_a=(team_a.rank if team_a else 50),
                rank_b=(team_b.rank if team_b else 50),
                group_context=group_context,
                odds_dict=fused,
                rule_result=rule,
                team_a=team_to_dict(team_a) if team_a else {},
                team_b=team_to_dict(team_b) if team_b else {},
                skip_wdl_resilience=True,
            )
            replay_triple = any(score_matches_pick(actual, p, eval_crs) for p in all_picks if p)
            n += 1
            if not stored_triple:
                stored_triple_miss += 1
                if replay_triple:
                    fixed += 1
                    print(f"FIXED {ta} vs {tb} actual={actual} stored={stored_all} replay={all_picks}")
                else:
                    replay_triple_miss += 1
                    print(f"STILL MISS {ta} vs {tb} actual={actual} replay={all_picks}")

        print(f"n={n} stored_triple_miss={stored_triple_miss} replay_fixed={fixed} still_miss={replay_triple_miss}")


if __name__ == "__main__":
    asyncio.run(main())
