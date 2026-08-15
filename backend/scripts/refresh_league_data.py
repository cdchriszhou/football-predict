#!/usr/bin/env python3
"""Refresh五大联赛 rosters and purge fake fixtures; sync from football-data when keyed.

Usage (from backend/):
  ./venv/bin/python scripts/refresh_league_data.py
  ./venv/bin/python scripts/refresh_league_data.py --sync
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.competitions import COMPETITIONS
from data.league_seed import ensure_league_data
from crawler.club_data_sync import sync_league_from_football_data
from crawler.football_data_client import _api_key
from db import async_session
from db.sqlite_write import commit_session


async def main(do_sync: bool) -> int:
    results = {}
    async with async_session() as db:
        for slug, comp in COMPETITIONS.items():
            if comp.get("type") != "club":
                continue
            seed = await ensure_league_data(db, slug)
            entry = {"seed": seed}
            if do_sync:
                if not _api_key():
                    entry["sync"] = {
                        "status": "skipped",
                        "reason": "FOOTBALL_DATA_API_KEY not configured",
                    }
                else:
                    entry["sync"] = await sync_league_from_football_data(db, slug)
            results[slug] = entry
        await commit_session(db)

    for slug, info in results.items():
        seed = info["seed"]
        sync = info.get("sync")
        print(
            f"[{slug}] teams={seed.get('teams')} removed={seed.get('teams_removed')} "
            f"purged_fixtures={seed.get('fixtures_purged')} "
            f"matches={seed.get('match_count')} real={seed.get('real_match_count')}"
        )
        if sync:
            print(f"  sync={sync.get('status')} detail={ {k: sync.get(k) for k in ('reason','teams','schedule','squads','removed_orphans') if k in sync} }")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Also pull standings/fixtures/squads from football-data.org",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.sync)))
