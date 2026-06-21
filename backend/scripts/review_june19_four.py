# -*- coding: utf-8 -*-
"""Review June 19 four-match predictions vs actual results."""
import asyncio
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select

from db import async_session
from db.models import Match, Prediction, Odds, Team
from api.predictions import _normalized_prediction_scores
from service.prediction_service import prepare_fused_odds

TARGETS = [
    ("美国", "澳大利亚"),
    ("苏格兰", "摩洛哥"),
    ("巴西", "海地"),
    ("土耳其", "巴拉圭"),
]

# Confirmed results (June 19/20 Beijing) from FIFA / news
ACTUAL = {
    ("美国", "澳大利亚"): (2, 0),
    ("苏格兰", "摩洛哥"): (0, 1),
    ("巴西", "海地"): (3, 0),
    ("土耳其", "巴拉圭"): (0, 1),
}


def outcome(score_a: int, score_b: int) -> str:
    if score_a > score_b:
        return "主胜"
    if score_a < score_b:
        return "客胜"
    return "平局"


def score_hit(actual: tuple[int, int], picks: list[str]) -> bool:
    s = f"{actual[0]}:{actual[1]}"
    return s in picks


def wdl_hit(actual: tuple[int, int], win: float, draw: float, lose: float) -> str:
    act = outcome(*actual)
    rates = {"主胜": win, "平局": draw, "客胜": lose}
    top = max(rates, key=rates.get)
    return "命中" if top == act else f"未中(预测{top} {rates[top]:.0f}%)"


async def main():
    async with async_session() as db:
        matches = (await db.execute(
            select(Match).where(Match.competition_slug == "worldcup-2026")
        )).scalars().all()
        by_pair = {(m.team_a, m.team_b): m for m in matches}

        report = []
        for home, away in TARGETS:
            m = by_pair.get((home, away))
            actual = ACTUAL[(home, away)]
            row = {
                "match": f"{home} vs {away}",
                "actual": f"{actual[0]}-{actual[1]} ({outcome(*actual)})",
                "db_result": None,
                "wdl": None,
                "scores": None,
                "upset": None,
                "confidence": None,
                "rank": None,
                "reason_snip": None,
            }
            if not m:
                row["error"] = "DB 未找到该对阵"
                report.append(row)
                continue

            if m.result_a is not None:
                row["db_result"] = f"{m.result_a}-{m.result_b}"

            pred = (await db.execute(
                select(Prediction)
                .where(Prediction.match_id == m.id)
                .order_by(Prediction.create_time.desc())
            )).scalars().first()
            odds_row = (await db.execute(
                select(Odds).where(Odds.match_id == m.id).order_by(Odds.id.desc())
            )).scalars().first()
            ta = (await db.execute(
                select(Team).where(
                    Team.competition_slug == m.competition_slug, Team.name == m.team_a
                )
            )).scalar_one_or_none()
            tb = (await db.execute(
                select(Team).where(
                    Team.competition_slug == m.competition_slug, Team.name == m.team_b
                )
            )).scalar_one_or_none()

            if pred:
                fused = prepare_fused_odds(odds_row, m.team_a, m.team_b) if odds_row else None
                norm = _normalized_prediction_scores(
                    pred,
                    crs=(fused or {}).get("score_odds"),
                    odds_row=odds_row,
                    rank_a=ta.rank if ta else None,
                    rank_b=tb.rank if tb else None,
                )
                picks = norm.get("best_scores") or []
                upset = norm.get("upset_score")
                row["wdl"] = {
                    "win": pred.win_rate,
                    "draw": pred.draw_rate,
                    "lose": pred.lose_rate,
                    "check": wdl_hit(actual, pred.win_rate, pred.draw_rate or 0, pred.lose_rate or 0),
                }
                row["scores"] = picks
                row["score_hit"] = score_hit(actual, picks + ([upset] if upset else []))
                row["upset"] = upset
                row["confidence"] = pred.confidence
                row["reason_snip"] = (pred.reason or "")[:200]
            row["rank"] = {
                home: ta.rank if ta else None,
                away: tb.rank if tb else None,
            }
            report.append(row)

    out_path = Path(__file__).resolve().parent / "_june19_review.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
