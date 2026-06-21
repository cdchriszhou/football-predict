# -*- coding: utf-8 -*-
"""Replay score_pick for 2026-06-17 World Cup matches (4 fixtures)."""
import json
import sqlite3

from service.score_backtest import run_score_prediction
from service.score_pick import score_matches_pick

MATCH_IDS = [17, 18, 19, 20]


def main():
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()
    hits = 0
    for mid in MATCH_IDS:
        cur.execute(
            "SELECT team_a, team_b, result_a, result_b, stage FROM matches WHERE id=?",
            (mid,),
        )
        ta, tb, ra, rb, stage = cur.fetchone()
        actual = f"{ra}:{rb}"
        cur.execute(
            "SELECT win_rate, draw_rate, lose_rate FROM predictions WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (mid,),
        )
        p = cur.fetchone()
        cur.execute(
            "SELECT score_odds, win_win, draw, win_lose, handicap FROM odds WHERE match_id=?",
            (mid,),
        )
        o = cur.fetchone()
        raw = json.loads(o[0])
        raw.pop("_meta", None)
        meta = {"win_win": o[1], "draw": o[2], "win_lose": o[3], "handicap": o[4]}
        p1, p2, upset, picks = run_score_prediction(
            ta, tb, raw, (p[0], p[1], p[2]), meta, stage=stage,
        )
        hit = any(score_matches_pick(actual, x, raw) for x in picks)
        hits += int(hit)
        print(f"{ta} vs {tb}  实际 {actual}")
        print(f"  推荐: {picks}  三选命中={'是' if hit else '否'}")
    print(f"\n合计: {hits}/{len(MATCH_IDS)} 三选命中")
    conn.close()


if __name__ == "__main__":
    main()
