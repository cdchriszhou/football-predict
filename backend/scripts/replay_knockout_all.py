"""Replay score picks for all finished 2026 knockout fixtures."""
from data.worldcup_history import HISTORICAL_MATCHES
from service.score_backtest import run_score_prediction, score_matches_pick


def main() -> None:
    hits = total = 0
    for h in HISTORICAL_MATCHES:
        if h.get("year") != 2026 or h.get("stage") not in ("1/16决赛", "1/8决赛"):
            continue
        if h.get("result_a") is None:
            continue
        total += 1
        crs = {str(k): float(v) for k, v in (h.get("score_odds") or {}).items()}
        eu = h.get("european") or {}
        if eu:
            w, d, l = eu["win_win"], eu["draw"], eu["win_lose"]
            o = 1 / w + 1 / d + 1 / l
            wdl = ((1 / w) / o * 100, (1 / d) / o * 100, (1 / l) / o * 100)
            odds = {
                "win_win": w, "draw": d, "win_lose": l,
                "handicap": (h.get("macau") or {}).get("handicap"),
            }
        else:
            ra, rb = h.get("rank_a", 50), h.get("rank_b", 50)
            gap = abs(ra - rb)
            if ra < rb:
                wdl = (55 + min(gap, 20), 28, 45 - min(gap, 20))
            else:
                wdl = (45 - min(gap, 20), 28, 55 + min(gap, 20))
            odds = None
        _, _, _, picks = run_score_prediction(
            h["team_a"], h["team_b"], crs, wdl, odds, stage=h["stage"],
        )
        actual = f"{h['result_a']}:{h['result_b']}"
        hit = any(score_matches_pick(actual, p, crs or None) for p in picks if p)
        hits += int(hit)
        print(
            f"{h['stage']} {h['team_a']} vs {h['team_b']} | actual={actual} | "
            f"picks={picks} | crs={'Y' if crs else 'N'} | hit={hit}",
        )
    print(f"\nKnockout triple-hit: {hits}/{total}")


if __name__ == "__main__":
    main()
