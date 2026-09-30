# -*- coding: utf-8 -*-
"""Review score picks for all started Big-Five leagues (current season)."""
from __future__ import annotations

import json
import sys
import sqlite3
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.competitions import COMPETITIONS, get_competition
from data.match_status import season_label_for
from service.score_backtest import (
    _ensure_crs_for_backtest,
    _evaluate_match,
    _parse_match_time,
    _parse_score_odds,
    _picks_from_db_prediction,
    run_score_prediction,
)
from service.score_pick import score_matches_pick

DB = ROOT / "worldcup2026.db"
OUT = Path(__file__).resolve().parent / "_all_leagues_score_review.json"

LEAGUE_SLUGS = [
    "premier-league",
    "la-liga",
    "serie-a",
    "bundesliga",
    "ligue-1",
]


def _pick_best_odds_row(group: list) -> tuple:
    best = None
    best_crs = {}
    for r in group:
        crs = _parse_score_odds(r["score_odds"])
        if crs and (not best_crs or len(crs) >= len(best_crs)):
            best, best_crs = r, crs
    if best is None:
        best = group[0]
        best_crs = _parse_score_odds(best["score_odds"])
    return best, best_crs


def review_league(con: sqlite3.Connection, slug: str, season: str) -> dict:
    rows = con.execute(
        """
        SELECT m.id, m.team_a, m.team_b, m.result_a, m.result_b,
               m.matchday, m.match_time, m.stage, m.group_name, m.location,
               p.best_score, p.win_rate, p.draw_rate, p.lose_rate,
               p.confidence, p.model_used,
               o.win_win, o.draw, o.win_lose, o.handicap, o.score_odds, o.source AS odds_source
        FROM matches m
        LEFT JOIN predictions p ON p.match_id = m.id
        LEFT JOIN odds o ON o.match_id = m.id
        WHERE m.competition_slug = ?
          AND m.season = ?
          AND m.result_a IS NOT NULL AND m.result_b IS NOT NULL
        ORDER BY m.match_time ASC, m.id ASC
        """,
        (slug, season),
    ).fetchall()

    by_match: dict[int, list] = {}
    for r in rows:
        by_match.setdefault(r["id"], []).append(r)

    details = []
    for mid, group in by_match.items():
        r, best_crs = _pick_best_odds_row(group)
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

        crs_for_run, crs_source = _ensure_crs_for_backtest(
            best_crs or {},
            team_a=r["team_a"],
            team_b=r["team_b"],
            stage=r["stage"] or "",
            wdl=wdl,
            odds_meta=odds_meta,
            competition_slug=slug,
        )

        replay = {
            "primary": None,
            "secondary": None,
            "upset": None,
            "hit_primary": None,
            "hit_any3": None,
        }
        if crs_source != "empty":
            p1, p2, upset, all_picks = run_score_prediction(
                r["team_a"],
                r["team_b"],
                crs_for_run,
                wdl,
                odds_meta,
                stage=r["stage"] or None,
                competition_slug=slug,
            )
            eval_crs = crs_for_run or {"1:0": 10.0}
            replay = {
                "primary": p1,
                "secondary": p2,
                "upset": upset,
                "hit_primary": score_matches_pick(actual, p1, eval_crs),
                "hit_any3": any(
                    score_matches_pick(actual, p, eval_crs) for p in all_picks if p
                ),
            }

        backtest = _evaluate_match(
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
            competition_slug=slug,
        )

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
                "hit_primary": backtest["primary_hit"] if backtest and published else None,
                "hit_any3": backtest["triple_hit"] if backtest and published else None,
            } if published else None,
            "replay": replay,
            "backtest_row": backtest,
        })

    pub = [d for d in details if d["published"]]
    rep = [d for d in details if d["replay"]["primary"] is not None]
    book = [d for d in rep if d["has_crs"]]
    syn = [d for d in rep if not d["has_crs"]]

    def _rate(xs, key_path_hit, key_path_any):
        n = len(xs)
        if not n:
            return {"n": 0, "primary_hits": 0, "primary_pct": None, "any3_hits": 0, "any3_pct": None}
        # key_path is like published/replay
        hp = sum(1 for d in xs if d[key_path_hit]["hit_primary"])
        ha = sum(1 for d in xs if d[key_path_any]["hit_any3"])
        return {
            "n": n,
            "primary_hits": hp,
            "primary_pct": round(hp / n, 3),
            "any3_hits": ha,
            "any3_pct": round(ha / n, 3),
        }

    # Outcome distribution of actuals
    outcomes = {"home": 0, "draw": 0, "away": 0}
    for d in details:
        a, b = map(int, d["actual"].split(":"))
        if a > b:
            outcomes["home"] += 1
        elif a == b:
            outcomes["draw"] += 1
        else:
            outcomes["away"] += 1

    # Replay pick bias: how often primary is home-win / draw / away-win
    replay_bias = {"home": 0, "draw": 0, "away": 0, "other": 0}
    for d in rep:
        p = d["replay"]["primary"] or ""
        if ":" not in p:
            replay_bias["other"] += 1
            continue
        a, b = map(int, p.split(":"))
        if a > b:
            replay_bias["home"] += 1
        elif a == b:
            replay_bias["draw"] += 1
        else:
            replay_bias["away"] += 1

    # Issues: book odds favor draw-ish but replay misses draw scores
    issues = []
    for d in details:
        if not d["replay"]["primary"]:
            continue
        a, b = map(int, d["actual"].split(":"))
        is_draw = a == b
        trio = [
            d["replay"]["primary"],
            d["replay"]["secondary"] if d["replay"]["secondary"] not in (None, "-") else None,
            d["replay"]["upset"],
        ]
        trio = [x for x in trio if x]
        has_draw_pick = any(":" in x and x.split(":")[0] == x.split(":")[1] for x in trio)
        euro = d["euro"]
        tight = False
        if euro[0] and euro[1] and euro[2]:
            try:
                # draw relatively short or home not heavy fav
                tight = float(euro[0]) >= 1.9 and float(euro[1]) <= 3.6
            except Exception:
                tight = False
        if is_draw and not d["replay"]["hit_any3"]:
            issues.append({
                "match": f"{d['home']} vs {d['away']}",
                "actual": d["actual"],
                "euro": euro,
                "replay": f"{d['replay']['primary']}/{d['replay']['secondary']}/{d['replay']['upset']}",
                "kind": "draw_miss",
                "has_draw_pick": has_draw_pick,
                "crs_source": d["crs_source"],
            })
        elif tight and not has_draw_pick and not d["replay"]["hit_any3"]:
            issues.append({
                "match": f"{d['home']} vs {d['away']}",
                "actual": d["actual"],
                "euro": euro,
                "replay": f"{d['replay']['primary']}/{d['replay']['secondary']}/{d['replay']['upset']}",
                "kind": "no_draw_in_trio",
                "has_draw_pick": False,
                "crs_source": d["crs_source"],
            })

    return {
        "slug": slug,
        "name": COMPETITIONS[slug]["short_name"],
        "season": season,
        "opening_date": COMPETITIONS[slug].get("opening_date"),
        "finished": len(details),
        "with_euro": sum(1 for d in details if d["euro"][0]),
        "with_crs": sum(1 for d in details if d["has_crs"]),
        "with_published": len(pub),
        "outcomes": outcomes,
        "summary": {
            "published": _rate(pub, "published", "published"),
            "replay_all": _rate(rep, "replay", "replay"),
            "replay_book_crs": _rate(book, "replay", "replay"),
            "replay_synthetic": _rate(syn, "replay", "replay"),
            "replay_bias": replay_bias,
        },
        "issues": issues[:12],
        "matches": details,
    }


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    leagues = []
    for slug in LEAGUE_SLUGS:
        comp = get_competition(slug)
        season = season_label_for(comp) if comp else "2026/27"
        leagues.append(review_league(con, slug, season))

    started = [L for L in leagues if L["finished"] > 0]
    not_started = [L for L in leagues if L["finished"] == 0]

    # Cross-league totals
    tot_fin = sum(L["finished"] for L in started)
    tot_pub = sum(L["with_published"] for L in started)
    tot_rep_n = sum(L["summary"]["replay_all"]["n"] for L in started)
    tot_rep_p = sum(L["summary"]["replay_all"]["primary_hits"] for L in started)
    tot_rep_3 = sum(L["summary"]["replay_all"]["any3_hits"] for L in started)
    tot_pub_p = sum(L["summary"]["published"]["primary_hits"] for L in started)
    tot_pub_3 = sum(L["summary"]["published"]["any3_hits"] for L in started)
    tot_pub_n = sum(L["summary"]["published"]["n"] for L in started)

    report = {
        "season": "2026/27",
        "started_leagues": [L["slug"] for L in started],
        "not_started_or_no_results": [L["slug"] for L in not_started],
        "totals": {
            "finished": tot_fin,
            "with_published": tot_pub,
            "published_primary": f"{tot_pub_p}/{tot_pub_n}" if tot_pub_n else "0/0",
            "published_any3": f"{tot_pub_3}/{tot_pub_n}" if tot_pub_n else "0/0",
            "replay_primary": f"{tot_rep_p}/{tot_rep_n}" if tot_rep_n else "0/0",
            "replay_any3": f"{tot_rep_3}/{tot_rep_n}" if tot_rep_n else "0/0",
            "replay_primary_pct": round(tot_rep_p / tot_rep_n, 3) if tot_rep_n else None,
            "replay_any3_pct": round(tot_rep_3 / tot_rep_n, 3) if tot_rep_n else None,
        },
        "leagues": leagues,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "started": report["started_leagues"],
        "no_results": report["not_started_or_no_results"],
        "totals": report["totals"],
        "per_league": [
            {
                "name": L["name"],
                "finished": L["finished"],
                "euro": L["with_euro"],
                "crs": L["with_crs"],
                "published": L["summary"]["published"],
                "replay": L["summary"]["replay_all"],
                "bias": L["summary"]["replay_bias"],
                "issues_n": len(L["issues"]),
            }
            for L in leagues
        ],
    }, ensure_ascii=False, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
