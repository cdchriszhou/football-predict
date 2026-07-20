"""Replay 1/16 score picks for completed knockout fixtures."""
from data.worldcup_history import HISTORICAL_MATCHES
from service.score_backtest import run_score_prediction, score_matches_pick

TARGETS = {("巴西", "日本"), ("德国", "巴拉圭"), ("荷兰", "摩洛哥")}

for h in HISTORICAL_MATCHES:
    if h.get("year") != 2026 or h.get("stage") != "1/16决赛":
        continue
    if (h["team_a"], h["team_b"]) not in TARGETS:
        continue
    crs = {str(k): float(v) for k, v in (h.get("score_odds") or {}).items()}
    eu = h.get("european") or {}
    w, d, l = eu["win_win"], eu["draw"], eu["win_lose"]
    o = 1 / w + 1 / d + 1 / l
    wdl = ((1 / w) / o * 100, (1 / d) / o * 100, (1 / l) / o * 100)
    p1, p2, upset, all_p = run_score_prediction(
        h["team_a"], h["team_b"], crs, wdl,
        {
            "win_win": w, "draw": d, "win_lose": l,
            "handicap": (h.get("macau") or {}).get("handicap"),
        },
        stage="1/16决赛",
    )
    actual = f"{h['result_a']}:{h['result_b']}"
    hit = score_matches_pick(actual, p1, crs) or any(
        score_matches_pick(actual, p, crs) for p in all_p if p
    )
    print(
        f"{h['team_a']} vs {h['team_b']} | actual={actual} | picks={all_p} | upset={upset} | hit={hit}",
    )
