"""Replay score pipeline for recent finished matches."""
from data.worldcup_history import HISTORICAL_MATCHES
from service.score_backtest import run_score_prediction, score_matches_pick


def eval_match(h):
    ta, tb = h["team_a"], h["team_b"]
    actual = f"{h['result_a']}:{h['result_b']}"
    crs = {str(k): float(v) for k, v in (h.get("score_odds") or {}).items()}
    eu = h.get("european") or {}
    odds_meta = {
        "win_win": eu.get("win_win"),
        "draw": eu.get("draw"),
        "win_lose": eu.get("win_lose"),
        "handicap": (h.get("macau") or {}).get("handicap"),
    }
    wdl = (55.0, 25.0, 20.0)
    if eu.get("win_win") and eu.get("draw") and eu.get("win_lose"):
        w, d, l = eu["win_win"], eu["draw"], eu["win_lose"]
        o = 1 / w + 1 / d + 1 / l
        wdl = ((1 / w) / o * 100, (1 / d) / o * 100, (1 / l) / o * 100)
    p1, p2, upset, all_p = run_score_prediction(
        ta, tb, crs, wdl, odds_meta, stage=h.get("stage"),
    )
    ph = score_matches_pick(actual, p1, crs)
    th = any(score_matches_pick(actual, p, crs) for p in all_p if p)
    return actual, p1, p2, upset, all_p, ph, th


if __name__ == "__main__":
    for date_prefix in ("2026-06-17", "2026-06-18"):
        print("===", date_prefix, "===")
        ms = [
            m for m in HISTORICAL_MATCHES
            if m.get("year") == 2026 and str(m.get("match_time", "")).startswith(date_prefix)
        ]
        ms.sort(key=lambda x: x.get("match_time", ""))
        for h in ms:
            actual, p1, p2, upset, all_p, ph, th = eval_match(h)
            print(
                f"{h['match_time']} {h['team_a']} vs {h['team_b']}",
                f"actual={actual}",
                f"picks={all_p}",
                f"primary={ph} triple={th}",
            )
        print()
