"""Review finished La Liga score picks for current season."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "worldcup2026.db"


def parse_best(raw):
    if not raw:
        return [], None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return [], None
    if isinstance(data, list):
        return [str(x) for x in data[:2]], None
    if isinstance(data, dict):
        scores = data.get("scores") or data.get("best_scores") or []
        upset = data.get("upset") or data.get("upset_score")
        return [str(x) for x in scores[:2]], (str(upset) if upset else None)
    return [], None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(matches)").fetchall()]
    pred_cols = [r[1] for r in con.execute("PRAGMA table_info(predictions)").fetchall()]
    odds_cols = [r[1] for r in con.execute("PRAGMA table_info(odds)").fetchall()]
    print("match_cols", cols)
    print("pred_cols", pred_cols)
    print("odds_cols", odds_cols)

    # detect team/result column names
    team_a = "team_a"
    team_b = "team_b"
    ra = "result_a"
    rb = "result_b"
    kick = "match_time"

    sql = f"""
    SELECT m.id, m.{team_a} AS home, m.{team_b} AS away,
           m.{ra} AS rh, m.{rb} AS ra,
           m.matchday, m.season, m.status, m.{kick} AS kickoff,
           p.best_score, p.win_rate, p.draw_rate, p.lose_rate,
           p.confidence, p.model_used
    FROM matches m
    LEFT JOIN predictions p ON p.match_id = m.id
    WHERE m.competition_slug = 'la-liga'
      AND m.season = '2026/27'
      AND m.{ra} IS NOT NULL AND m.{rb} IS NOT NULL
    ORDER BY m.{kick} ASC
    """
    rows = con.execute(sql).fetchall()
    print(f"\nFinished 2026/27 La Liga: {len(rows)}\n")

    for r in rows:
        scores, upset = parse_best(r["best_score"])
        actual = f"{r['rh']}:{r['ra']}"
        primary = scores[0] if scores else None
        secondary = scores[1] if len(scores) > 1 else None
        trio = [x for x in [primary, secondary, upset] if x]
        hit_p = primary == actual
        hit3 = actual in trio
        odds = con.execute(
            "SELECT * FROM odds WHERE match_id = ?", (r["id"],)
        ).fetchone()
        has_crs = False
        euro = None
        if odds:
            okeys = odds.keys()
            raw_crs = odds["score_odds"] if "score_odds" in okeys else None
            if raw_crs:
                try:
                    crs = json.loads(raw_crs) if isinstance(raw_crs, str) else raw_crs
                    has_crs = bool(crs)
                except Exception:
                    has_crs = False
            euro = (odds["win_win"], odds["draw"], odds["win_lose"])

        print("=" * 72)
        print(f"MD{r['matchday']} | {r['home']} vs {r['away']}")
        print(f"  kickoff={r['kickoff']}  result={actual}")
        print(f"  picks: primary={primary} secondary={secondary} upset={upset}")
        print(f"  hit_primary={hit_p} hit_any3={hit3}")
        print(
            f"  wdl%={r['win_rate']}/{r['draw_rate']}/{r['lose_rate']} "
            f"conf={r['confidence']} model={r['model_used']}"
        )
        print(f"  has_crs={has_crs} euro={euro}")

    with_pred = [r for r in rows if r["best_score"]]
    n = len(with_pred)
    hp = hs = h3 = 0
    for r in with_pred:
        scores, upset = parse_best(r["best_score"])
        actual = f"{r['rh']}:{r['ra']}"
        primary = scores[0] if scores else None
        secondary = scores[1] if len(scores) > 1 else None
        if primary == actual:
            hp += 1
        if secondary == actual:
            hs += 1
        if actual in [x for x in [primary, secondary, upset] if x]:
            h3 += 1
    print("\n" + "=" * 72)
    print(f"SUMMARY stored predictions: {n}/{len(rows)}")
    if n:
        print(f"  primary hit: {hp}/{n} = {hp/n:.0%}")
        print(f"  secondary hit: {hs}/{n}")
        print(f"  any-of-3 hit: {h3}/{n} = {h3/n:.0%}")

    all_fin = con.execute(
        f"""SELECT season, COUNT(*) c FROM matches
            WHERE competition_slug='la-liga' AND {ra} IS NOT NULL AND {rb} IS NOT NULL
            GROUP BY season ORDER BY season"""
    ).fetchall()
    print("finished by season:", [dict(x) for x in all_fin])


if __name__ == "__main__":
    main()
