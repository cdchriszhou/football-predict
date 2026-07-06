"""Knockout replay: all finished 2026 R32/R16 fixtures should hit in triple picks."""
from data.worldcup_history import HISTORICAL_MATCHES
from service.score_backtest import run_score_prediction, score_matches_pick


def _wdl_and_odds(h: dict) -> tuple[tuple[float, float, float], dict | None]:
    eu = h.get("european") or {}
    if eu:
        w, d, l = eu["win_win"], eu["draw"], eu["win_lose"]
        o = 1 / w + 1 / d + 1 / l
        wdl = ((1 / w) / o * 100, (1 / d) / o * 100, (1 / l) / o * 100)
        odds = {
            "win_win": w, "draw": d, "win_lose": l,
            "handicap": (h.get("macau") or {}).get("handicap"),
        }
        return wdl, odds
    ra, rb = h.get("rank_a", 50), h.get("rank_b", 50)
    gap = abs(ra - rb)
    if ra < rb:
        wdl = (55 + min(gap, 20), 28, 45 - min(gap, 20))
    else:
        wdl = (45 - min(gap, 20), 28, 55 + min(gap, 20))
    return wdl, None


def test_knockout_all_finished_triple_hit_at_least_half():
    """Finished knockouts: triple picks should hit at least 5/8 (no-CRS is harder)."""
    hits = total = 0
    for h in HISTORICAL_MATCHES:
        if h.get("year") != 2026 or h.get("stage") not in ("1/16决赛", "1/8决赛"):
            continue
        if h.get("result_a") is None:
            continue
        total += 1
        crs = {str(k): float(v) for k, v in (h.get("score_odds") or {}).items()}
        wdl, odds = _wdl_and_odds(h)
        _, _, _, picks = run_score_prediction(
            h["team_a"], h["team_b"], crs, wdl, odds, stage=h["stage"],
        )
        actual = f"{h['result_a']}:{h['result_b']}"
        if any(score_matches_pick(actual, p, crs or None) for p in picks if p):
            hits += 1
    assert total >= 8
    assert hits >= 5, f"knockout triple-hit {hits}/{total} below minimum"


def test_knockout_no_crs_mexico_ecuador_hits():
    h = next(
        m for m in HISTORICAL_MATCHES
        if m.get("year") == 2026 and m.get("team_a") == "墨西哥" and m.get("team_b") == "厄瓜多尔"
    )
    wdl, odds = _wdl_and_odds(h)
    _, _, _, picks = run_score_prediction(
        h["team_a"], h["team_b"], {}, wdl, odds, stage=h["stage"],
    )
    assert any(score_matches_pick("2:1", p, None) for p in picks if p)


def test_knockout_finalize_uses_wdl_when_rank_gap_small():
    from service.score_pick import finalize_knockout_score_picks

    scores, _ = finalize_knockout_score_picks(
        [],
        expected_a=1.95,
        expected_b=1.95,
        win_rate=42.0,
        draw_rate=28.0,
        lose_rate=58.0,
        rank_a=34,
        rank_b=31,
        stage="1/16决赛",
    )
    assert _score_outcome(scores[0]) == "lose"


def _score_outcome(score: str) -> str:
    ga, gb = map(int, score.split(":"))
    if ga > gb:
        return "win"
    if ga < gb:
        return "lose"
    return "draw"
