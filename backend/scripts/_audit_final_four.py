# -*- coding: utf-8 -*-
"""Replay semi-finals and upcoming final with full production path."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from sqlalchemy import select

from db import async_session
from db.models import Match, Odds, Prediction, Team
from service.prediction_service import prepare_fused_odds, team_to_dict
from service.score_pick import run_full_score_pipeline, _rank_crs, _score_outcome
from service.match_context import build_group_context
from service.calibration_service import CalibratedRuleEngine


async def analyze_match(db, match_id: int):
    m = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one()
    odds = (await db.execute(
        select(Odds).where(Odds.match_id == match_id).order_by(Odds.id.desc())
    )).scalars().first()
    pred = (await db.execute(
        select(Prediction).where(Prediction.match_id == match_id)
        .order_by(Prediction.create_time.desc()).limit(1)
    )).scalar_one_or_none()
    ta = (await db.execute(
        select(Team).where(Team.competition_slug == m.competition_slug, Team.name == m.team_a)
    )).scalar_one_or_none()
    tb = (await db.execute(
        select(Team).where(Team.competition_slug == m.competition_slug, Team.name == m.team_b)
    )).scalar_one_or_none()
    fused = prepare_fused_odds(odds, m.team_a, m.team_b) if odds else {}
    crs = {k: v for k, v in (fused.get("score_odds") or {}).items() if not str(k).startswith("_")}
    ctx = build_group_context(
        m.stage, m.group_name or "", 0, m.team_a, m.team_b,
        ta.rank if ta else 50, tb.rank if tb else 50,
    )
    engine = CalibratedRuleEngine()
    rule = engine.evaluate(
        team_to_dict(ta) if ta else {"name": m.team_a, "rank": 50},
        team_to_dict(tb) if tb else {"name": m.team_b, "rank": 50},
        odds=fused, group_context=ctx,
    )
    stored = None
    if pred and pred.best_score:
        raw = pred.best_score
        if isinstance(raw, str):
            raw = json.loads(raw)
        stored = raw

    print(f"\n=== {m.stage}: {m.team_a} vs {m.team_b} ({m.result_a}:{m.result_b}) status={m.status} ===")
    print(f"Ranks: {ta.rank if ta else '?'} vs {tb.rank if tb else '?'}")
    if odds:
        print(f"SPF: {odds.win_win}/{odds.draw}/{odds.win_lose} hcp={odds.handicap}")
    print(f"Rule WDL: {rule.win_rate:.1f}/{rule.draw_rate:.1f}/{rule.lose_rate:.1f}")
    if pred:
        print(f"Stored WDL: {pred.win_rate:.1f}/{pred.draw_rate:.1f}/{pred.lose_rate:.1f}")
        print(f"Stored scores: {stored}")
    if crs:
        top = _rank_crs(crs, set())[:5]
        print(f"CRS top5: {top}")
        print(f"CRS fav outcome: {_score_outcome(top[0][0]) if top else '?'}")
    else:
        print("CRS: MISSING in DB")

    if crs:
        scores, upset, picks, warns = run_full_score_pipeline(
            crs,
            win_rate=pred.win_rate if pred else rule.win_rate,
            draw_rate=pred.draw_rate if pred else rule.draw_rate,
            lose_rate=pred.lose_rate if pred else rule.lose_rate,
            expected_a=rule.expected_a,
            expected_b=rule.expected_b,
            model_scores=rule.best_scores,
            stage=m.stage,
            sp_win=fused.get("win_win"),
            sp_draw=fused.get("draw"),
            sp_lose=fused.get("win_lose"),
            handicap=fused.get("handicap"),
            rank_a=ta.rank if ta else 50,
            rank_b=tb.rank if tb else 50,
            group_context=ctx,
            odds_dict=fused,
            rule_result=rule,
            team_a=team_to_dict(ta) if ta else None,
            team_b=team_to_dict(tb) if tb else None,
            skip_wdl_resilience=True,
        )
        print(f"Replay pipeline: primary={scores} upset={upset} picks={picks}")
        if warns:
            print(f"Warnings: {warns[:3]}")


async def main():
    # semi-finals + upcoming
    ids = [2106, 2107, 2108, 2109]
    async with async_session() as db:
        for mid in ids:
            await analyze_match(db, mid)


if __name__ == "__main__":
    asyncio.run(main())
