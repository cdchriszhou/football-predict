# -*- coding: utf-8 -*-
import asyncio
import json
import sqlite3
from datetime import datetime

from crawler.sporttery_client import fetch_sporttery_on_sale, find_sporttery_match, to_db_odds
from service.score_pick import pick_crs_anchored_scores, pick_upset_from_crs
from utils.score_prediction import normalize_score_prediction


def main():
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.id, m.team_a, m.team_b, m.match_time, m.result_a, m.result_b, m.status
        FROM matches m
        WHERE m.competition_slug='worldcup-2026'
          AND m.match_time >= '2026-06-15 00:00:00'
          AND m.match_time < '2026-06-16 00:00:00'
        ORDER BY m.match_time
        """
    )
    rows = cur.fetchall()
    print("=== June 15 matches ===")
    for r in rows:
        mid, ta, tb, mt, ra, rb, st = r
        cur.execute(
            "SELECT win_rate, draw_rate, lose_rate, best_score, reason FROM predictions WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (mid,),
        )
        p = cur.fetchone()
        actual = f"{ra}:{rb}" if ra is not None and rb is not None else "?"
        pred_scores = json.loads(p[3]) if p and p[3] else []
        upset = None
        if p and p[3]:
            # upset may be in best_score json structure
            pass
        cur.execute("SELECT score_odds, win_win, draw, win_lose, source FROM odds WHERE match_id=?", (mid,))
        o = cur.fetchone()
        print(f"\n{ta} vs {tb} | actual={actual} status={st}")
        if p:
            print(f"  WDL={p[0]:.1f}/{p[1]:.1f}/{p[2]:.1f}% pred={pred_scores}")
        if o and o[0]:
            raw = json.loads(o[0])
            meta = raw.pop("_meta", {})
            st_odds = {"win_win": o[1], "draw": o[2], "win_lose": o[3]}
            print(f"  odds source={o[4]} spf={st_odds}")
            if raw:
                ranked = sorted(
                    [(k, float(v)) for k, v in raw.items() if ":" in str(k)],
                    key=lambda x: x[1],
                )[:5]
                print(f"  top CRS: {ranked}")
    conn.close()


if __name__ == "__main__":
    main()
