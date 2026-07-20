# -*- coding: utf-8 -*-
"""Re-predict all upcoming matches (skip cache, write fresh DB rows)."""
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

from data.status_constants import MATCH_UPCOMING
from db import async_session, init_db
from db.models import Match, Prediction
from service.prediction_service import PredictionService
from utils.score_prediction import parse_best_score_payload


async def main() -> None:
    await init_db()
    service = PredictionService()
    refreshed = 0
    failed: list[tuple[int, str]] = []

    async with async_session() as db:
        matches = (
            await db.execute(
                select(Match)
                .where(
                    Match.competition_slug == "worldcup-2026",
                    Match.status == MATCH_UPCOMING,
                )
                .order_by(Match.match_time)
            )
        ).scalars().all()

        print(f"Upcoming matches to re-predict: {len(matches)}\n")

        for m in matches:
            label = f"{m.team_a} vs {m.team_b}"
            old = (
                await db.execute(
                    select(Prediction)
                    .where(Prediction.match_id == m.id)
                    .order_by(Prediction.create_time.desc())
                )
            ).scalars().first()
            old_payload = parse_best_score_payload(old.best_score if old else None)

            try:
                result = await service.predict_match(
                    m.id, db, model="rule_engine", skip_cache=True,
                )
                if not result:
                    failed.append((m.id, label))
                    print(f"  FAIL (empty) {label}")
                    continue
                refreshed += 1
                new_scores = result.get("best_scores") or []
                new_upset = result.get("upset_score")
                print(f"  OK {label}")
                print(f"     old: {old_payload.get('scores')} upset={old_payload.get('upset')}")
                print(f"     new: {new_scores} upset={new_upset}")
                print(
                    f"     WDL: {result.get('win_rate'):.1f}/"
                    f"{result.get('draw_rate'):.1f}/"
                    f"{result.get('lose_rate'):.1f}"
                )
            except Exception as exc:
                failed.append((m.id, label))
                print(f"  FAIL {label}: {exc}")

    print(f"\nDone: {refreshed}/{len(matches)} refreshed, {len(failed)} failed")
    if failed:
        print("Failed:", json.dumps(failed, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
