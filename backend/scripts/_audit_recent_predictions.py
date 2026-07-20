# -*- coding: utf-8 -*-
"""Audit recent score predictions: stored vs replay, new vs legacy pipeline."""
from __future__ import annotations

import asyncio
import sys
from collections import defaultdict

from sqlalchemy import select

from db import async_session
from db.models import Match, Odds, Prediction, Team
from service.calibration_service import CalibratedRuleEngine
from service.match_context import build_group_context
from service.prediction_service import infer_matchday, prepare_fused_odds, team_to_dict
from service.score_backtest import (
    _best_odds_with_crs,
    _find_history_for_match,
    _picks_from_db_prediction,
    score_matches_pick,
)
from service.score_pick import run_full_score_pipeline
from service.score_pick_config import get_config, load_config
from data.knockout_advance import display_teams_for_match, load_knockout_slot_index_cached


def _safe_print(msg: str) -> None:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


async def _replay_match(
    match,
    pred,
    ko_index,
    db,
    *,
    use_new: bool,
) -> tuple[list[str], str | None]:
    engine = CalibratedRuleEngine()
    ta, tb = display_teams_for_match(match, ko_index)
    ta, tb = ta or match.team_a, tb or match.team_b
    all_odds = (
        await db.execute(select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc()))
    ).scalars().all()
    odds_row, crs = _best_odds_with_crs(list(all_odds))
    hist = _find_history_for_match(ta, tb, stage=match.stage or "", match_time=match.match_time)
    if not crs and hist:
        crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
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
    load_config({"PIPELINE_USE_NEW_ENSEMBLE": use_new})
    try:
        best, upset, all_picks, _ = run_full_score_pipeline(
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
    finally:
        load_config()
    return all_picks, upset


async def main():
    cfg = get_config()
    _safe_print(f"PIPELINE_USE_NEW_ENSEMBLE={cfg.get('PIPELINE_USE_NEW_ENSEMBLE')}")
    _safe_print(f"RESILIENCE bumps: cs={cfg.get('RESILIENCE_CLEAN_SHEET_BUMP')} drought={cfg.get('RESILIENCE_SCORING_DROUGHT_BUMP')}")

    async with async_session() as db:
        ko_index = await load_knockout_slot_index_cached(db, "worldcup-2026")
        matches = (
            await db.execute(
                select(Match)
                .where(
                    Match.competition_slug == "worldcup-2026",
                    Match.result_a.isnot(None),
                    Match.result_b.isnot(None),
                )
                .order_by(Match.match_time.desc())
            )
        ).scalars().all()

        stats = defaultdict(lambda: {"n": 0, "stored_t": 0, "new_t": 0, "legacy_t": 0})
        misses: list[str] = []

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
            actual = f"{match.result_a}:{match.result_b}"
            ta, tb = display_teams_for_match(match, ko_index)
            ta, tb = ta or match.team_a, tb or match.team_b
            all_odds = (
                await db.execute(select(Odds).where(Odds.match_id == match.id).order_by(Odds.id.desc()))
            ).scalars().all()
            _, crs = _best_odds_with_crs(list(all_odds))
            hist = _find_history_for_match(ta, tb, stage=match.stage or "", match_time=match.match_time)
            if not crs and hist:
                crs = {str(k): float(v) for k, v in (hist.get("score_odds") or {}).items()}
            eval_crs = crs or {"1:0": 10.0}
            _, _, _, stored_all = published
            stored_t = any(score_matches_pick(actual, p, eval_crs) for p in stored_all if p)
            new_picks, _ = await _replay_match(match, pred, ko_index, db, use_new=True)
            legacy_picks, _ = await _replay_match(match, pred, ko_index, db, use_new=False)
            new_t = any(score_matches_pick(actual, p, eval_crs) for p in new_picks if p)
            legacy_t = any(score_matches_pick(actual, p, eval_crs) for p in legacy_picks if p)
            stg = match.stage or "小组赛"
            g = stats[stg]
            g["n"] += 1
            g["stored_t"] += int(stored_t)
            g["new_t"] += int(new_t)
            g["legacy_t"] += int(legacy_t)
            if not stored_t:
                misses.append(
                    f"{stg} {ta} vs {tb} actual={actual} "
                    f"stored={stored_all} new={new_picks} legacy={legacy_picks} "
                    f"crs={'Y' if crs else 'N'} wdl={pred.win_rate:.0f}/{pred.draw_rate:.0f}/{pred.lose_rate:.0f}"
                )

        _safe_print("\n=== By stage (triple hit rate) ===")
        for stg, g in sorted(stats.items()):
            n = g["n"]
            _safe_print(
                f"{stg}: n={n} stored={g['stored_t']/n*100:.0f}% "
                f"new={g['new_t']/n*100:.0f}% legacy={g['legacy_t']/n*100:.0f}%"
            )

        _safe_print("\n=== Recent stored misses (last 20) ===")
        for line in misses[:20]:
            _safe_print(line)


if __name__ == "__main__":
    asyncio.run(main())
