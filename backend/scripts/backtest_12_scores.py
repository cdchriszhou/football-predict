# -*- coding: utf-8 -*-
"""Backtest score picks on confirmed 2026 group matches (full CRS pipeline)."""
import json
import sqlite3

from service.score_backtest import run_score_prediction, _history_row, _odds_meta_from_history
from service.score_pick import score_matches_pick

CASES = [
    ("墨西哥", "南非", "2:0"),
    ("韩国", "捷克", "2:1"),
    ("加拿大", "波黑", "1:1"),
    ("美国", "巴拉圭", "4:1"),
    ("卡塔尔", "瑞士", "1:1"),
    ("巴西", "摩洛哥", "1:1"),
    ("海地", "苏格兰", "0:1"),
    ("澳大利亚", "土耳其", "2:0"),
    ("德国", "库拉索", "7:1"),
    ("荷兰", "日本", "2:2"),
    ("科特迪瓦", "厄瓜多尔", "1:0"),
    ("瑞典", "突尼斯", "5:1"),
    ("西班牙", "佛得角", "0:0"),
    ("比利时", "埃及", "1:1"),
    ("沙特阿拉伯", "乌拉圭", "1:1"),
    ("伊朗", "新西兰", "2:2"),
]


def _load_db_odds(ta, tb):
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()
    cur.execute(
        "SELECT m.id FROM matches m WHERE m.team_a=? AND m.team_b=? AND m.competition_slug='worldcup-2026'",
        (ta, tb),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None, None, None
    mid = row[0]
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
    conn.close()
    if not o or not o[0]:
        return None, p, None
    raw = json.loads(o[0])
    raw.pop("_meta", None)
    odds = {"win_win": o[1], "draw": o[2], "win_lose": o[3], "handicap": o[4]}
    return raw, p, odds


def main():
    primary_hits = triple_hits = 0
    print(f"{'比赛':<22} {'实际':<6} {'首推':<6} {'次推':<6} {'冷门':<6} 命中")
    print("-" * 70)
    for ta, tb, actual in CASES:
        hist = _history_row(ta, tb)
        crs, wdl, odds_meta = _load_db_odds(ta, tb)
        if not crs and hist:
            crs = hist.get("score_odds")
            odds_meta = _odds_meta_from_history(hist)
        if not wdl and hist:
            wdl = (50, 25, 25)
        p1, p2, upset, all_p = run_score_prediction(ta, tb, crs or {}, wdl, odds_meta)
        ph = score_matches_pick(actual, p1, crs)
        th = any(score_matches_pick(actual, p, crs) for p in all_p)
        primary_hits += ph
        triple_hits += th
        mark = "✅首推" if ph else ("✅三选" if th else "❌")
        print(f"{ta+' vs '+tb:<22} {actual:<6} {p1:<6} {p2:<6} {(upset or '-'):<6} {mark}")
    n = len(CASES)
    print("-" * 70)
    print(f"首推 {primary_hits}/{n}  三选 {triple_hits}/{n}")


if __name__ == "__main__":
    main()
