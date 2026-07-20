# -*- coding: utf-8 -*-
"""Diagnose score prediction pipeline for user-listed misses."""
import json
import sqlite3

from crawler.schedule_crawler import _build_expected_matches
from crawler.team_crawler import TEAM_DATA
from data.worldcup_history import HISTORICAL_MATCHES, rank_to_abilities
from scripts.backtest_12_scores import _load_db_odds
from service.score_backtest import run_score_prediction, _history_row, _odds_meta_from_history
from service.score_pick import score_matches_pick

CASES = [
    ("加拿大", "波黑", "1:1"),
    ("卡塔尔", "瑞士", "1:1"),
    ("美国", "巴拉圭", "4:1"),
    ("澳大利亚", "土耳其", "2:0"),
    ("德国", "库拉索", "7:1"),
    ("科特迪瓦", "厄瓜多尔", "1:0"),
    ("瑞典", "突尼斯", "5:1"),
    ("西班牙", "佛得角", "0:0"),
    ("伊朗", "新西兰", "2:2"),
]


def _hist(ta, tb):
    for m in HISTORICAL_MATCHES:
        if m.get("year") == 2026 and m["team_a"] == ta and m["team_b"] == tb:
            return m
    return None


def main():
    expected = {(m["team_a"], m["team_b"]): m for m in _build_expected_matches()}
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()

    print(f"{'比赛':<22} {'实际':<6} {'首推':<6} {'次推':<6} {'冷门':<8} {'命中':<6} 地点OK")
    print("-" * 90)
    for ta, tb, actual in CASES:
        hist = _hist(ta, tb)
        crs, wdl, odds = _load_db_odds(ta, tb)
        if not crs and hist:
            crs = hist.get("score_odds") or {}
            euro = hist.get("european") or {}
            macau = hist.get("macau") or {}
            odds = {
                "win_win": euro.get("win_win"),
                "draw": euro.get("draw"),
                "win_lose": euro.get("win_lose"),
                "handicap": macau.get("handicap"),
            }
        p1, p2, upset, all_p = run_score_prediction(ta, tb, crs or {}, wdl, odds)
        ph = score_matches_pick(actual, p1, crs)
        th = any(score_matches_pick(actual, p, crs) for p in all_p if p)
        mark = "首推" if ph else ("三选" if th else "MISS")
        cur.execute(
            "SELECT location, stadium FROM matches WHERE team_a=? AND team_b=? AND competition_slug=?",
            (ta, tb, "worldcup-2026"),
        )
        db_loc = cur.fetchone()
        exp = expected.get((ta, tb), {})
        loc_ok = "Y" if db_loc and exp and db_loc[0] == exp.get("location") and db_loc[1] == exp.get("stadium") else "N"
        if hist and db_loc:
            hloc = hist.get("location"), hist.get("stadium")
            if hloc[0] and (db_loc[0] != hloc[0] or db_loc[1] != hloc[1]):
                loc_ok = f"hist:{hloc[0]}"
        print(f"{ta+' vs '+tb:<22} {actual:<6} {p1:<6} {p2:<6} {(upset or '-'):<8} {mark:<6} {loc_ok}")
    conn.close()


if __name__ == "__main__":
    main()
