"""Replay score pipeline for 2026-06-19 (Beijing) Group A/B matchday 2."""
import sys
sys.path.insert(0, ".")

from service.score_backtest import run_score_prediction, score_matches_pick
from service.score_pick import run_full_score_pipeline
from service.score_backtest import _expected_goals
from crawler.team_crawler import TEAM_DATA

# Pre-match CRS snapshots (approximate from SPF + typical sporttery structure)
MATCHES = [
    {
        "team_a": "捷克", "team_b": "南非", "actual": "1:1",
        "european": {"win_win": 2.15, "draw": 3.15, "win_lose": 3.40},
        "handicap": "0",
        "crs": {
            "1:1": 5.80, "1:0": 6.50, "0:1": 7.00, "2:1": 9.00, "1:2": 10.0,
            "0:0": 8.50, "2:0": 11.0, "0:2": 12.0, "2:2": 14.0,
        },
        "matchday": 2, "group": "A",
    },
    {
        "team_a": "瑞士", "team_b": "波黑", "actual": "4:1",
        "european": {"win_win": 1.48, "draw": 4.20, "win_lose": 6.50},
        "handicap": "-1",
        "crs": {
            "2:0": 5.50, "1:0": 6.00, "2:1": 6.50, "1:1": 7.50, "3:0": 8.00,
            "3:1": 9.50, "4:1": 14.0, "4:0": 16.0, "0:0": 12.0, "1:2": 18.0,
            "胜其它": 22.0,
        },
        "matchday": 2, "group": "B",
    },
    {
        "team_a": "加拿大", "team_b": "卡塔尔", "actual": "6:0",
        "european": {"win_win": 1.18, "draw": 6.50, "win_lose": 12.0},
        "handicap": "-2",
        "crs": {
            "3:0": 5.50, "2:0": 6.00, "4:0": 7.00, "3:1": 8.50, "4:1": 10.0,
            "5:0": 11.0, "2:1": 9.00, "1:0": 9.50, "6:0": 18.0, "胜其它": 25.0,
        },
        "matchday": 2, "group": "B",
    },
    {
        "team_a": "墨西哥", "team_b": "韩国", "actual": "1:0",
        "european": {"win_win": 1.72, "draw": 3.45, "win_lose": 4.80},
        "handicap": "-0.5",
        "crs": {
            "1:0": 6.00, "2:0": 7.50, "1:1": 6.50, "2:1": 8.00, "0:0": 9.00,
            "3:0": 11.0, "0:1": 12.0, "1:2": 14.0, "2:2": 15.0,
        },
        "matchday": 2, "group": "A",
    },
]


def wdl_from_eu(eu):
    w, d, l = eu["win_win"], eu["draw"], eu["win_lose"]
    o = 1 / w + 1 / d + 1 / l
    return ((1 / w) / o * 100, (1 / d) / o * 100, (1 / l) / o * 100)


def main():
    for m in MATCHES:
        eu = m["european"]
        wdl = wdl_from_eu(eu)
        odds_meta = {**eu, "handicap": m["handicap"]}
        p1, p2, upset, picks = run_score_prediction(
            m["team_a"], m["team_b"], m["crs"], wdl, odds_meta, stage="小组赛",
        )
        actual = m["actual"]
        ph = score_matches_pick(actual, p1, m["crs"])
        th = any(score_matches_pick(actual, p, m["crs"]) for p in picks if p)
        ra = TEAM_DATA[m["team_a"]]["rank"]
        rb = TEAM_DATA[m["team_b"]]["rank"]
        ea, eb = _expected_goals(m["team_a"], m["team_b"])
        print("=" * 55)
        print(f"{m['team_a']} vs {m['team_b']}  actual={actual}")
        print(f"WDL={wdl[0]:.1f}/{wdl[1]:.1f}/{wdl[2]:.1f}  xG={ea}/{eb}  ranks {ra}/{rb}")
        print(f"Picks: {picks}  primary_hit={ph}  triple_hit={th}")


if __name__ == "__main__":
    main()
