# -*- coding: utf-8 -*-
"""Replay score_pick for June 15 (night 4) matches."""
import asyncio
import json
import sqlite3

from service.score_pick import pick_crs_anchored_scores, pick_upset_from_crs


MATCHES = [
    ("德国", "库拉索", "7:1"),
    ("荷兰", "日本", "2:2"),
    ("科特迪瓦", "厄瓜多尔", "1:0"),
    ("瑞典", "突尼斯", "5:1"),
]


def load(mid_filter=None):
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()
    for ta, tb, actual in MATCHES:
        cur.execute(
            "SELECT id FROM matches WHERE team_a=? AND team_b=? AND competition_slug='worldcup-2026'",
            (ta, tb),
        )
        row = cur.fetchone()
        if not row:
            print(f"MISSING {ta} vs {tb}")
            continue
        mid = row[0]
        cur.execute(
            "SELECT win_rate, draw_rate, lose_rate, best_score FROM predictions WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (mid,),
        )
        p = cur.fetchone()
        cur.execute("SELECT score_odds, win_win, draw, win_lose FROM odds WHERE match_id=?", (mid,))
        o = cur.fetchone()
        pred = json.loads(p[3]) if p and p[3] else {}
        scores = pred.get("scores") or pred.get("best_scores") or []
        upset = pred.get("upset") or pred.get("upset_score")
        raw = {}
        sp_win = sp_draw = sp_lose = None
        if o:
            sp_win, sp_draw, sp_lose = o[1], o[2], o[3]
            if o[0]:
                raw = json.loads(o[0])
                raw.pop("_meta", None)
        print(f"\n{'='*60}")
        print(f"{ta} vs {tb}  实际 {actual}")
        print(f"  存储预测: 首推={scores[0] if scores else '?'} 次推={scores[1] if len(scores)>1 else '-'} 冷门={upset}")
        print(f"  WDL={p[0]:.1f}/{p[1]:.1f}/{p[2]:.1f}%  SPF={sp_win}/{sp_draw}/{sp_lose}")
        ranked = sorted(
            [(k, float(v)) for k, v in raw.items() if ":" in str(k) and float(v) > 1.01],
            key=lambda x: x[1],
        )[:8]
        print(f"  CRS最低8项: {ranked}")
        if actual in [s for s, _ in ranked]:
            pos = [i for i, (s, _) in enumerate(ranked) if s == actual]
            print(f"  实际比分在CRS前8: {'是 #' + str(pos[0]+1) if pos else '否'}")
        # replay without model hints
        replay = pick_crs_anchored_scores(
            raw,
            win_rate=p[0],
            lose_rate=p[2],
            draw_rate=p[1],
            sp_win=sp_win,
            sp_lose=sp_lose,
        )
        replay_upset = pick_upset_from_crs(
            raw, replay,
            win_rate=p[0], lose_rate=p[2], draw_rate=p[1],
            sp_win=sp_win, sp_lose=sp_lose,
        )
        print(f"  算法重放: 首推={replay[0]} 次推={replay[1] if len(replay)>1 else '-'} 冷门={replay_upset}")
        hit = actual in (replay + [replay_upset])
        hit_stored = actual in (scores + ([upset] if upset else []))
        print(f"  重放三选命中={hit}  存储三选命中={hit_stored}")
    conn.close()


if __name__ == "__main__":
    load()
