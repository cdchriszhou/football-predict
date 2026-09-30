# -*- coding: utf-8 -*-
"""Sync backtest-style review for finished 2026/27 La Liga matches."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from service.score_backtest import (
    _ensure_crs_for_backtest,
    _evaluate_match,
    _parse_match_time,
    _parse_score_odds,
    _picks_from_db_prediction,
    run_score_prediction,
)

DB = ROOT / "worldcup2026.db"
OUT = Path(__file__).resolve().parent / "_laliga_score_review.json"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT m.id, m.team_a, m.team_b, m.result_a, m.result_b,
               m.matchday, m.match_time, m.stage, m.group_name, m.location,
               p.best_score, p.win_rate, p.draw_rate, p.lose_rate,
               p.confidence, p.model_used,
               o.id AS odds_id, o.win_win, o.draw, o.win_lose,
               o.handicap, o.score_odds, o.source AS odds_source
        FROM matches m
        LEFT JOIN predictions p ON p.match_id = m.id
        LEFT JOIN odds o ON o.match_id = m.id
        WHERE m.competition_slug = 'la-liga'
          AND m.season = '2026/27'
          AND m.result_a IS NOT NULL AND m.result_b IS NOT NULL
        ORDER BY m.match_time ASC, m.id ASC
        """
    ).fetchall()

    # collapse duplicate odds joins: prefer row with CRS
    by_match: dict[int, list] = {}
    for r in rows:
        by_match.setdefault(r["id"], []).append(r)

    evaluated = []
    details = []
    for mid, group in by_match.items():
        # pick best odds among group
        best = None
        best_crs = {}
        for r in group:
            crs = _parse_score_odds(r["score_odds"])
            if crs and (not best_crs or len(crs) >= len(best_crs)):
                best, best_crs = r, crs
        if best is None:
            best = group[0]
            best_crs = _parse_score_odds(best["score_odds"])

        r = best
        actual = f"{r['result_a']}:{r['result_b']}"
        odds_meta = None
        if r["win_win"] or r["draw"] or r["win_lose"]:
            odds_meta = {
                "win_win": r["win_win"],
                "draw": r["draw"],
                "win_lose": r["win_lose"],
                "handicap": r["handicap"],
            }
        wdl = None
        if r["win_rate"] is not None:
            wdl = (r["win_rate"], r["draw_rate"], r["lose_rate"])

        published = None
        if r["best_score"]:
            published = _picks_from_db_prediction(SimpleNamespace(best_score=r["best_score"]))

        # Always also compute pure replay (current algorithm)
        crs_for_run, crs_source = _ensure_crs_for_backtest(
            best_crs or {},
            team_a=r["team_a"],
            team_b=r["team_b"],
            stage=r["stage"] or "",
            wdl=wdl,
            odds_meta=odds_meta,
            competition_slug="la-liga",
        )
        replay_p1 = replay_p2 = replay_upset = None
        replay_hit_p = replay_hit3 = None
        if crs_source != "empty":
            replay_p1, replay_p2, replay_upset, replay_all = run_score_prediction(
                r["team_a"],
                r["team_b"],
                crs_for_run,
                wdl,
                odds_meta,
                stage=r["stage"] or None,
                competition_slug="la-liga",
            )
            from service.score_pick import score_matches_pick
            eval_crs = crs_for_run or {"1:0": 10.0}
            replay_hit_p = score_matches_pick(actual, replay_p1, eval_crs)
            replay_hit3 = any(
                score_matches_pick(actual, p, eval_crs) for p in replay_all if p
            )

        row = _evaluate_match(
            team_a=r["team_a"],
            team_b=r["team_b"],
            actual=actual,
            crs=best_crs,
            wdl=wdl,
            odds_meta=odds_meta,
            match_id=r["id"],
            match_time=_parse_match_time(r["match_time"]),
            stage=r["stage"] or "",
            group_name=r["group_name"],
            matchday=r["matchday"],
            location=r["location"],
            published_picks=published,
            competition_slug="la-liga",
        )
        if row:
            evaluated.append(row)

        details.append({
            "match_id": mid,
            "matchday": r["matchday"],
            "kickoff": r["match_time"],
            "home": r["team_a"],
            "away": r["team_b"],
            "actual": actual,
            "euro": [r["win_win"], r["draw"], r["win_lose"]],
            "has_crs": bool(best_crs),
            "crs_source": crs_source,
            "stored_wdl": wdl,
            "confidence": r["confidence"],
            "model": r["model_used"],
            "published": {
                "primary": published[0] if published else None,
                "secondary": published[1] if published else None,
                "upset": published[2] if published else None,
                "hit_primary": row["primary_hit"] if row and published else None,
                "hit_any3": row["triple_hit"] if row and published else None,
            } if published else None,
            "replay": {
                "primary": replay_p1,
                "secondary": replay_p2,
                "upset": replay_upset,
                "hit_primary": replay_hit_p,
                "hit_any3": replay_hit3,
            },
            "backtest_row": row,
        })

    def rate(items, pkey, tkey):
        xs = [d for d in items if d.get(pkey) is not None]
        n = len(xs)
        if not n:
            return {"n": 0}
        hp = sum(1 for d in xs if d[pkey])
        ht = sum(1 for d in xs if d[tkey])
        return {
            "n": n,
            "primary_hits": hp,
            "primary_pct": round(hp / n, 3),
            "any3_hits": ht,
            "any3_pct": round(ht / n, 3),
        }

    pub = [d for d in details if d["published"]]
    rep = [d for d in details if d["replay"]["primary"] is not None]
    summary = {
        "finished": len(details),
        "evaluated_backtest": len(evaluated),
        "published": rate(
            [{"p": d["published"]["hit_primary"], "t": d["published"]["hit_any3"]} for d in pub],
            "p",
            "t",
        ) if False else {
            "n": len(pub),
            "primary_hits": sum(1 for d in pub if d["published"]["hit_primary"]),
            "primary_pct": round(sum(1 for d in pub if d["published"]["hit_primary"]) / len(pub), 3) if pub else 0,
            "any3_hits": sum(1 for d in pub if d["published"]["hit_any3"]),
            "any3_pct": round(sum(1 for d in pub if d["published"]["hit_any3"]) / len(pub), 3) if pub else 0,
        },
        "replay_all": {
            "n": len(rep),
            "primary_hits": sum(1 for d in rep if d["replay"]["hit_primary"]),
            "primary_pct": round(sum(1 for d in rep if d["replay"]["hit_primary"]) / len(rep), 3) if rep else 0,
            "any3_hits": sum(1 for d in rep if d["replay"]["hit_any3"]),
            "any3_pct": round(sum(1 for d in rep if d["replay"]["hit_any3"]) / len(rep), 3) if rep else 0,
        },
        "replay_with_book_crs": {
            "n": sum(1 for d in rep if d["has_crs"]),
            "primary_hits": sum(1 for d in rep if d["has_crs"] and d["replay"]["hit_primary"]),
            "any3_hits": sum(1 for d in rep if d["has_crs"] and d["replay"]["hit_any3"]),
        },
        "replay_synthetic": {
            "n": sum(1 for d in rep if not d["has_crs"]),
            "primary_hits": sum(1 for d in rep if not d["has_crs"] and d["replay"]["hit_primary"]),
            "any3_hits": sum(1 for d in rep if not d["has_crs"] and d["replay"]["hit_any3"]),
        },
    }

    report = {"summary": summary, "matches": details}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("---")
    for d in details:
        pub_s = "-"
        if d["published"]:
            pub_s = f"{d['published']['primary']}/{d['published']['secondary']}/{d['published']['upset']}"
        print(
            f"MD{d['matchday']} {d['home']} vs {d['away']} = {d['actual']} | "
            f"pub {pub_s} | "
            f"replay {d['replay']['primary']}/{d['replay']['secondary']}/{d['replay']['upset']} "
            f"hitP={d['replay']['hit_primary']} hit3={d['replay']['hit_any3']} "
            f"crs={d['crs_source']} euro={d['euro']}"
        )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
