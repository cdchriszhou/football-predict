# -*- coding: utf-8 -*-
"""Replay last-night / latest Big Five score picks with current pipeline."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.league_seed import LEAGUE_TEAMS
from service.match_context import build_group_context
from service.rule_engine import RuleEngine
from service.score_backtest import (
    _parse_score_odds,
    _wdl_from_european,
    run_score_prediction,
)
from service.score_pick import run_full_score_pipeline, score_matches_pick

DB = ROOT / "worldcup2026.db"
OUT = Path(__file__).resolve().parent / "_last_night_replay.json"

RANK = {
    slug: {name: rank for name, _en, rank in teams}
    for slug, teams in LEAGUE_TEAMS.items()
}


def _club(name: str, rank: int) -> dict:
    pct = max(0.0, 1.0 - (rank - 1) / 19.0)
    base = 62 + pct * 28
    return {
        "name": name,
        "rank": rank,
        "attack": round(base + pct * 6),
        "defend": round(base - (1 - pct) * 4),
        "midfield": round(base),
        "speed": round(base - 2),
        "physical": round(base - 1),
        "tactic": "传控",
    }


def _top_crs(crs: dict, n: int = 8) -> list:
    ranked = sorted(crs.items(), key=lambda kv: kv[1])
    return [{"score": s, "odd": o} for s, o in ranked[:n]]


def _outcome(score: str) -> str:
    a, b = map(int, score.split(":"))
    if a > b:
        return "home"
    if a < b:
        return "away"
    return "draw"


def replay_with_ranks(r: sqlite3.Row, crs: dict, wdl, odds_meta) -> dict:
    slug = r["competition_slug"]
    ra = RANK.get(slug, {}).get(r["team_a"], 10)
    rb = RANK.get(slug, {}).get(r["team_b"], 10)
    home = _club(r["team_a"], ra)
    away = _club(r["team_b"], rb)
    md = int(r["matchday"] or 1)
    stage = r["stage"] or f"第{md}轮"
    ctx = build_group_context(
        stage, "", md, r["team_a"], r["team_b"], ra, rb, home_side_override="a",
    )
    has_book = bool(odds_meta and odds_meta.get("win_win"))
    ctx["has_book_odds"] = has_book

    engine = RuleEngine()
    rule = engine.evaluate(home, away, group_context=ctx)
    wr, dr, lr = wdl if wdl else (rule.win_rate, rule.draw_rate, rule.lose_rate)
    if wdl:
        # blend slightly toward rule so xG and WDL are consistent
        pass

    book_crs = dict(crs) if crs else {}
    use_crs = book_crs
    if not use_crs:
        from service.score_pick import poisson_to_synthetic_crs
        use_crs = poisson_to_synthetic_crs(rule.expected_a, rule.expected_b, dr)

    odds_dict = {
        "win_win": (odds_meta or {}).get("win_win"),
        "draw": (odds_meta or {}).get("draw"),
        "win_lose": (odds_meta or {}).get("win_lose"),
        "has_real_market": has_book,
    }
    best, upset, picks, warns = run_full_score_pipeline(
        use_crs,
        win_rate=wr,
        draw_rate=dr,
        lose_rate=lr,
        expected_a=rule.expected_a,
        expected_b=rule.expected_b,
        stage=stage,
        sp_win=(odds_meta or {}).get("win_win"),
        sp_draw=(odds_meta or {}).get("draw"),
        sp_lose=(odds_meta or {}).get("win_lose"),
        handicap=(odds_meta or {}).get("handicap"),
        rank_a=ra,
        rank_b=rb,
        group_context=ctx,
        odds_dict=odds_dict,
        team_a=home,
        team_b=away,
        rule_result=rule,
    )
    actual = f"{r['result_a']}:{r['result_b']}"
    eval_crs = use_crs or {"1:0": 10.0}
    p1 = best[0] if best else None
    p2 = best[1] if best and len(best) > 1 else None
    return {
        "ranks": [ra, rb],
        "rule_wdl": [round(rule.win_rate, 1), round(rule.draw_rate, 1), round(rule.lose_rate, 1)],
        "rule_xg": [round(rule.expected_a, 2), round(rule.expected_b, 2)],
        "used_wdl": [round(wr, 1), round(dr, 1), round(lr, 1)],
        "crs_source": "book" if book_crs else "synthetic",
        "top_crs": _top_crs(use_crs),
        "primary": p1,
        "secondary": p2,
        "upset": upset,
        "hit_primary": bool(p1 and score_matches_pick(actual, p1, eval_crs)),
        "hit_any3": any(score_matches_pick(actual, p, eval_crs) for p in picks if p),
        "warnings": warns[:6],
    }


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ids = (2506, 2878, 2504, 2879, 2119, 2505)
    rows = con.execute(
        f"""
        SELECT m.id, m.competition_slug, m.matchday, m.stage, m.match_time,
               m.team_a, m.team_b, m.result_a, m.result_b,
               o.win_win, o.draw, o.win_lose, o.handicap, o.score_odds
        FROM matches m
        LEFT JOIN odds o ON o.match_id = m.id
        WHERE m.id IN ({",".join("?" * len(ids))})
        ORDER BY m.match_time
        """,
        ids,
    ).fetchall()

    by_id: dict[int, list] = {}
    for r in rows:
        by_id.setdefault(r["id"], []).append(r)

    details = []
    for mid in sorted(by_id, key=lambda i: by_id[i][0]["match_time"]):
        group = by_id[mid]
        best, best_crs = None, {}
        for r in group:
            crs = _parse_score_odds(r["score_odds"])
            if crs and (not best_crs or len(crs) >= len(best_crs)):
                best, best_crs = r, crs
        if best is None:
            best = group[0]
            best_crs = _parse_score_odds(best["score_odds"])
        r = best
        odds_meta = None
        if r["win_win"] or r["draw"] or r["win_lose"]:
            odds_meta = {
                "win_win": r["win_win"],
                "draw": r["draw"],
                "win_lose": r["win_lose"],
                "handicap": r["handicap"],
            }
        inferred = _wdl_from_european(odds_meta)
        actual = f"{r['result_a']}:{r['result_b']}"

        naive = {
            "primary": None,
            "secondary": None,
            "upset": None,
            "hit_primary": None,
            "hit_any3": None,
        }
        if inferred or best_crs:
            p1, p2, upset, all_picks = run_score_prediction(
                r["team_a"], r["team_b"], best_crs or {}, inferred, odds_meta,
                stage=r["stage"] or None,
                competition_slug=r["competition_slug"],
                matchday=r["matchday"],
            )
            eval_crs = best_crs or {"1:0": 10.0}
            naive = {
                "primary": p1,
                "secondary": p2,
                "upset": upset,
                "hit_primary": score_matches_pick(actual, p1, eval_crs) if p1 else None,
                "hit_any3": any(score_matches_pick(actual, p, eval_crs) for p in all_picks if p),
            }

        ranked = replay_with_ranks(r, best_crs, inferred, odds_meta)
        details.append({
            "id": mid,
            "league": r["competition_slug"],
            "md": r["matchday"],
            "kickoff": r["match_time"],
            "home": r["team_a"],
            "away": r["team_b"],
            "actual": actual,
            "actual_out": _outcome(actual),
            "euro": [r["win_win"], r["draw"], r["win_lose"]],
            "handicap": r["handicap"],
            "implied_wdl": [round(x, 1) for x in inferred] if inferred else None,
            "naive_backtest_10_10": naive,
            "ranked_replay": ranked,
        })

    OUT.write_text(json.dumps({"matches": details}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    for d in details:
        rr = d["ranked_replay"]
        print(
            f"{d['league']} {d['home']} {d['actual']} {d['away']} | "
            f"euro={d['euro']} | ranked {rr['primary']}/{rr['secondary']}/{rr['upset']} "
            f"hit_p={rr['hit_primary']} any3={rr['hit_any3']} xG={rr['rule_xg']} "
            f"crs={rr['crs_source']} top={rr['top_crs'][:3]}"
        )


if __name__ == "__main__":
    main()
