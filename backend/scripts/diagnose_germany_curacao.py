"""Diagnose sporttery odds for Germany vs Curaçao."""
import asyncio
import json
import sqlite3
from datetime import datetime

from crawler.sporttery_client import (
    fetch_sporttery_on_sale,
    find_sporttery_match,
    sporttery_row_has_sale_data,
    to_db_odds,
)
from service.sporttery_resolve import resolve_sporttery_for_match
from db.models import Match


def load_db_match():
    conn = sqlite3.connect("worldcup2026.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, team_a, team_b, match_time, status, group_name
        FROM matches
        WHERE (team_a LIKE '%德国%' AND team_b LIKE '%库拉索%')
           OR (team_a LIKE '%库拉索%' AND team_b LIKE '%德国%')
        """
    )
    rows = cur.fetchall()
    print("=== DB matches Germany vs Curacao ===")
    for r in rows:
        print(r)
        mid = r[0]
        cur.execute(
            "SELECT id, win_win, draw, win_lose, source, update_time FROM odds WHERE match_id=?",
            (mid,),
        )
        odds = cur.fetchall()
        print("  odds:", odds)
        if odds:
            cur.execute("SELECT score_odds FROM odds WHERE match_id=?", (mid,))
            so = cur.fetchone()[0]
            if so:
                d = json.loads(so)
                meta = d.get("_meta", {})
                print("  meta sources:", meta.get("sources"))
                print("  sporttery meta:", meta.get("sporttery"))
    conn.close()
    return rows


async def check_sporttery(rows):
    pool = await fetch_sporttery_on_sale(force_refresh=True)
    print(f"\n=== Sporttery pool size: {len(pool)} ===")
    related = [
        m
        for m in pool
        if "德国" in (m.get("home_team", "") + m.get("away_team", ""))
        or "库拉索" in (m.get("home_team", "") + m.get("away_team", ""))
    ]
    print(f"Germany/Curacao related in pool: {len(related)}")
    for m in related:
        print(
            f"  {m.get('match_num')} {m['home_team']} vs {m['away_team']} "
            f"kickoff={m.get('kickoff')} league={m.get('league')} had={m.get('had')}"
        )

    if not rows:
        print("\nNo DB row for Germany vs Curacao")
        return

    if rows:
        from datetime import datetime

        team_a, team_b, match_time, mid = rows[0][1], rows[0][2], rows[0][3], rows[0][0]
        if isinstance(match_time, str):
            mt = datetime.fromisoformat(match_time.replace("Z", ""))
        else:
            mt = match_time

        fake_match = Match(
            id=mid,
            team_a=team_a,
            team_b=team_b,
            match_time=mt,
            competition_slug="worldcup-2026",
        )
        resolved = await resolve_sporttery_for_match(fake_match, pool=pool)
        print(f"\n=== resolve_sporttery_for_match ===")
        print(f"  resolved={resolved is not None}")
        if resolved:
            print(f"  on_sale={resolved.get('on_sale')} win={resolved.get('win_win')}")
            print(f"  handicap={resolved.get('handicap')} crs={len(resolved.get('score_odds') or {})}")


def main():
    rows = load_db_match()
    asyncio.run(check_sporttery(rows))


if __name__ == "__main__":
    main()
