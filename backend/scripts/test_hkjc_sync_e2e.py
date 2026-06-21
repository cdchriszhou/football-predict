"""Run HKJC sync end-to-end like the API endpoint."""
import asyncio
import traceback

from db import async_session, init_db
from service.hkjc_backtest import compute_backtest
from service.hkjc_sync import sync_active_meetings, sync_race_results


async def main():
    await init_db()
    async with async_session() as db:
        try:
            print("=== sync_active_meetings ===")
            meetings = await sync_active_meetings(db, force=True, commit=True)
            print(f"meetings synced: {len(meetings)}")
            for m in meetings[:3]:
                print(f"  - {m.get('id')} {m.get('date')} {m.get('venue')} races={m.get('race_count')}")

            print("=== sync_race_results (7 days) ===")
            n = await sync_race_results(db, days=7, max_races_per_day=11, commit=True)
            print(f"results synced: {n}")

            print("=== backtest ===")
            bt = await compute_backtest(db)
            print(f"evaluated: {bt.get('races_evaluated')} win_rate: {bt.get('win_hit_rate')}")
            print("SUCCESS")
        except Exception as e:
            print("FAILED:", type(e).__name__, e)
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
