#!/usr/bin/env python3
"""Diagnose why HKJC horse profiles are empty or missing age/rating/sex."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from db import async_session
from db.models import HkjcMeetingCache, HkjcRaceResult
from service.hkjc_sync import (
    _aggregate_horses_from_rows,
    _horse_profiles_incomplete,
    _json_loads,
    _meeting_has_runners,
    _ratings_mostly_missing,
    ensure_horse_catalog,
    list_horses,
    refresh_horse_profiles_in_cache,
)


async def main() -> None:
    async with async_session() as db:
        cache_n = (await db.execute(select(func.count()).select_from(HkjcMeetingCache))).scalar() or 0
        result_n = (await db.execute(select(func.count()).select_from(HkjcRaceResult))).scalar() or 0

        print(f"HkjcMeetingCache rows: {cache_n}")
        print(f"HkjcRaceResult rows: {result_n}")

        all_rows = (await db.execute(select(HkjcMeetingCache))).scalars().all()
        stub = runner = incomplete_meetings = 0
        sources: dict[str, int] = {}
        for row in all_rows:
            data = _json_loads(row.payload)
            src = data.get("source") or row.source or "unknown"
            sources[src] = sources.get(src, 0) + 1
            if _meeting_has_runners(data):
                runner += 1
                if _horse_profiles_incomplete(_aggregate_horses_from_rows([row])):
                    incomplete_meetings += 1
            else:
                stub += 1
        print(f"Cache sources: {sources}")
        print(f"Meetings with runners: {runner}, empty stubs: {stub}")
        print(f"Meetings with sparse runner fields: {incomplete_meetings}")

        horses = _aggregate_horses_from_rows(all_rows)
        print(f"Horses aggregated (cache only): {len(horses)}")
        with_age = sum(1 for h in horses.values() if int(h.get("age") or 0) > 0)
        with_sex = sum(1 for h in horses.values() if h.get("sex"))
        with_rating = sum(1 for h in horses.values() if int(h.get("rating") or 0) > 0)
        print(f"  with age: {with_age}, with sex: {with_sex}, with rating>0: {with_rating}")
        if horses:
            sample = horses[next(iter(horses))]
            print(
                f"Sample: name={sample.get('name')} age={sample.get('age')} "
                f"sex={sample.get('sex')} rating={sample.get('rating')}"
            )
        print(f"Catalog sparse: {_horse_profiles_incomplete(horses)}")
        print(f"Ratings mostly missing: {_ratings_mostly_missing(horses)}")

        if "--full" in sys.argv:
            print("\n--- list_horses(ensure=True, refresh=False) [max ~3 min] ---")
            try:
                listed = await asyncio.wait_for(
                    list_horses(db, refresh_profiles=False, ensure=True),
                    timeout=200.0,
                )
            except asyncio.TimeoutError:
                print("TIMEOUT — use: python scripts/diagnose_hkjc_horses.py --refresh-ratings")
                return
            print(f"Returned horses: {len(listed)}")
            wr = sum(1 for h in listed if int(h.get("rating") or 0) > 0)
            print(f"  with rating>0: {wr}")
            if listed:
                h = listed[0]
                print(f"First: {h.get('name')} age={h.get('age')} sex={h.get('sex')} rating={h.get('rating')}")
        else:
            print("\n(Skip network — run with --full or --refresh-ratings to test HKJC fetch)")

        print("\nTip: rating=0 often means cache built from赛果 only, or 評分+/- column was parsed wrong.")
        print("After deploy fix: python scripts/diagnose_hkjc_horses.py --refresh-ratings")


async def run_refresh_ratings() -> None:
    async with async_session() as db:
        print("Refreshing racecard profiles for 2 recent meetings (max 90s)...")
        try:
            n = await asyncio.wait_for(
                refresh_horse_profiles_in_cache(db, max_meetings=2, commit=True),
                timeout=90.0,
            )
            print(f"Updated meetings: {n}")
        except asyncio.TimeoutError:
            print("TIMEOUT — check outbound access to racing.hkjc.com")
            return
        horses = _aggregate_horses_from_rows(
            (await db.execute(select(HkjcMeetingCache))).scalars().all()
        )
        wr = sum(1 for h in horses.values() if int(h.get("rating") or 0) > 0)
        print(f"Horses: {len(horses)}, with rating>0: {wr}")


async def run_sync() -> None:
    async with async_session() as db:
        n = await asyncio.wait_for(ensure_horse_catalog(db, max_sync=2, commit=True), timeout=180.0)
        print(f"ensure_horse_catalog synced meetings: {n}")


if __name__ == "__main__":
    if "--refresh-ratings" in sys.argv:
        asyncio.run(run_refresh_ratings())
    elif "--sync" in sys.argv:
        asyncio.run(run_sync())
    else:
        asyncio.run(main())
