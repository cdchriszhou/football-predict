# -*- coding: utf-8 -*-
"""Diagnose June 22 (Beijing) four-match score prediction misses."""
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from db import async_session
from db.models import Match, Prediction, Odds, Team
from service.prediction_service import prepare_fused_odds, team_to_dict
from service.score_pick import run_full_score_pipeline, score_matches_pick
from service.match_context import build_group_context
from data.worldcup_group_standings import load_group_standings

ACTUAL = {
    ("西班牙", "沙特阿拉伯"): "4:0",
    ("比利时", "伊朗"): "0:0",
    ("乌拉圭", "佛得角"): "2:2",
    ("新西兰", "埃及"): "1:3",
}


async def main():
    report = []
    async with async_session() as db:
        for (ta, tb), actual in ACTUAL.items():
            m = (await db.execute(
                select(Match).where(Match.team_a == ta, Match.team_b == tb)
            )).scalar_one_or_none()
            if not m:
                continue
            pred = (await db.execute(
                select(Prediction).where(Prediction.match_id == m.id)
                .order_by(Prediction.create_time.desc())
            )).scalars().first()
            odds = (await db.execute(
                select(Odds).where(Odds.match_id == m.id).order_by(Odds.id.desc())
            )).scalars().first()
            ta_obj = (await db.execute(
                select(Team).where(Team.competition_slug == m.competition_slug, Team.name == ta)
            )).scalar_one_or_none()
            tb_obj = (await db.execute(
                select(Team).where(Team.competition_slug == m.competition_slug, Team.name == tb)
            )).scalar_one_or_none()
            fused = prepare_fused_odds(odds, ta, tb) if odds else {}
            crs = {k: v for k, v in (fused.get("score_odds") or {}).items() if not str(k).startswith("_")}
            payload = json.loads(pred.best_score) if pred and pred.best_score else {}
            stored = (payload.get("scores") or []) + ([payload["upset"]] if payload.get("upset") else [])
            wdl = (pred.win_rate, pred.draw_rate or 0, pred.lose_rate)
            matchday = 2
            standings = None
            if m.group_name:
                standings = await load_group_standings(db, m.competition_slug, m.group_name, m.match_time)
            ctx = build_group_context(
                m.stage, m.group_name or "", matchday, ta, tb,
                ta_obj.rank if ta_obj else 50, tb_obj.rank if tb_obj else 50,
                location=m.location or "", standings=standings,
            )
            best, upset, allp, warns = run_full_score_pipeline(
                crs,
                win_rate=wdl[0], draw_rate=wdl[1], lose_rate=wdl[2],
                sp_win=odds.win_win if odds else None,
                sp_draw=odds.draw if odds else None,
                sp_lose=odds.win_lose if odds else None,
                handicap=odds.handicap if odds else None,
                rank_a=ta_obj.rank if ta_obj else None,
                rank_b=tb_obj.rank if tb_obj else None,
                odds_dict=fused,
                stage=m.stage,
                group_context=ctx,
                team_a=team_to_dict(ta_obj) if ta_obj else {"name": ta},
                team_b=team_to_dict(tb_obj) if tb_obj else {"name": tb},
                model_scores=payload.get("scores"),
            )
            row = {
                "match": f"{ta} vs {tb}",
                "actual": actual,
                "stored": stored,
                "stored_hit": any(score_matches_pick(actual, p, crs) for p in stored if p),
                "replay": best + ([upset] if upset else []),
                "replay_hit": any(score_matches_pick(actual, p, crs) for p in (best + ([upset] if upset else []))),
                "wdl": wdl,
                "spf": [odds.win_win, odds.draw, odds.win_lose] if odds else None,
                "handicap": odds.handicap if odds else None,
                "ou": odds.over_under if odds else None,
                "ctx_keys": {k: v for k, v in ctx.items() if k.startswith(("standing_", "must_", "group_", "both_"))},
                "crs_draw": {k: crs[k] for k in ("0:0", "1:1", "2:2") if k in crs},
                "actual_odd": crs.get(actual),
            }
            report.append(row)

    out = Path(__file__).resolve().parent / "_june22_review.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in report:
        print("=" * 60)
        print(r["match"], "actual", r["actual"])
        print("  stored", r["stored"], "hit", r["stored_hit"])
        print("  replay", r["replay"], "hit", r["replay_hit"])
        print("  wdl", r["wdl"], "spf", r["spf"], "hc", r["handicap"])
        print("  ctx", json.dumps(r["ctx_keys"], ensure_ascii=False))
        print("  draw crs", r["crs_draw"], "actual odd", r["actual_odd"])


if __name__ == "__main__":
    asyncio.run(main())
