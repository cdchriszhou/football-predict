# -*- coding: utf-8 -*-
import json
import sqlite3

from crawler.team_crawler import TEAM_DATA
from service.score_pick import (
    apply_favourite_blowout_scores,
    boost_heavy_favorite_scores,
    pick_crs_anchored_scores,
    pick_upset_from_crs,
    promote_strong_home_multi_goal,
    score_matches_pick,
)

CASES = [
    ("西班牙", "佛得角", "0:0"),
    ("比利时", "埃及", "1:1"),
    ("沙特阿拉伯", "乌拉圭", "1:1"),
    ("伊朗", "新西兰", "2:2"),
]


def main():
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()
    for ta, tb, actual in CASES:
        cur.execute("SELECT m.id FROM matches m WHERE team_a=? AND team_b=? LIMIT 1", (ta, tb))
        mid = cur.fetchone()[0]
        cur.execute(
            "SELECT win_rate, draw_rate, lose_rate FROM predictions WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (mid,),
        )
        wr, dr, lr = cur.fetchone()
        cur.execute(
            "SELECT score_odds, win_win, draw, win_lose, handicap FROM odds WHERE match_id=?",
            (mid,),
        )
        o = cur.fetchone()
        crs = json.loads(o[0])
        crs.pop("_meta", None)
        sp = {"win_win": o[1], "draw": o[2], "win_lose": o[3], "handicap": o[4]}
        ra, rb = TEAM_DATA[ta]["rank"], TEAM_DATA[tb]["rank"]
        draws = sorted(
            [(k, v) for k, v in crs.items() if ":" in str(k) and k.split(":")[0] == k.split(":")[1]],
            key=lambda x: x[1],
        )
        print(f"\n{ta} vs {tb} actual={actual} wr={wr:.1f} dr={dr:.1f} lr={lr:.1f} rank={ra}-{rb} hcp={sp['handicap']}")
        print("draws CRS:", draws[:8])
        print("0:0:", crs.get("0:0"), " 2:2:", crs.get("2:2"))
        best = pick_crs_anchored_scores(
            crs, win_rate=wr, lose_rate=lr, draw_rate=dr,
            sp_win=sp["win_win"], sp_draw=sp["draw"], sp_lose=sp["win_lose"],
        )
        for label, fn in [
            ("anchor", lambda b: b),
            ("boost", lambda b: boost_heavy_favorite_scores(b, crs, win_rate=wr, handicap=sp["handicap"], rank_a=ra, rank_b=rb)),
            ("blowout", lambda b: apply_favourite_blowout_scores(b, crs, sp_win=sp["win_win"], handicap=sp["handicap"], win_rate=wr, lose_rate=lr)),
            ("promote", lambda b: promote_strong_home_multi_goal(b, crs, sp_win=sp["win_win"])),
        ]:
            if label == "anchor":
                best = fn(best)
            else:
                best = fn(best)
            print(f"  {label}: {best}")
        upset = pick_upset_from_crs(
            crs, best, win_rate=wr, lose_rate=lr, draw_rate=dr,
            sp_win=sp["win_win"], sp_lose=sp["win_lose"],
            handicap=sp["handicap"],
            rank_a=ra, rank_b=rb,
        )
        all_p = best + ([upset] if upset else [])
        hit = any(score_matches_pick(actual, p, crs) for p in all_p)
        print(f"  upset: {upset}  hit={hit}")
    conn.close()


if __name__ == "__main__":
    main()
