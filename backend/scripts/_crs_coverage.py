import asyncio
from sqlalchemy import select
from db import async_session
from db.models import Match, Odds
from service.score_backtest import _best_odds_with_crs

async def main():
    async with async_session() as db:
        rows = (await db.execute(
            select(Match).where(Match.competition_slug == "worldcup-2026", Match.result_a.isnot(None))
            .order_by(Match.match_time)
        )).scalars().all()
        by_stage = {}
        for m in rows:
            st = m.stage or "group"
            odds = (await db.execute(select(Odds).where(Odds.match_id == m.id))).scalars().all()
            _, crs = _best_odds_with_crs(list(odds))
            g = by_stage.setdefault(st, {"n": 0, "crs": 0})
            g["n"] += 1
            if crs:
                g["crs"] += 1
        for st, g in sorted(by_stage.items()):
            pct = g["crs"] / g["n"] * 100
            print(f"{st}: {g['crs']}/{g['n']} have CRS ({pct:.0f}%)")

asyncio.run(main())
