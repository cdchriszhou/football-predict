# -*- coding: utf-8 -*-
"""Audit stored Big-Five exact-score predictions for 2026/27."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "worldcup2026.db"
OUT = Path(__file__).resolve().parent / "_five_league_stored_audit.json"

SLUGS = [
    "premier-league",
    "la-liga",
    "serie-a",
    "bundesliga",
    "ligue-1",
]


def _parse_best(raw: str | None):
    if not raw:
        return None, None, None
    try:
        data = json.loads(raw)
    except Exception:
        return None, None, None
    if isinstance(data, dict):
        scores = data.get("scores") or []
        upset = data.get("upset")
        p1 = scores[0] if len(scores) > 0 else None
        p2 = scores[1] if len(scores) > 1 else None
        return p1, p2, upset
    if isinstance(data, list):
        p1 = data[0] if data else None
        p2 = data[1] if len(data) > 1 else None
        return p1, p2, None
    return None, None, None


def _wdl(score: str) -> str:
    a, b = map(int, score.split(":"))
    if a > b:
        return "H"
    if a < b:
        return "A"
    return "D"


def _goals(score: str) -> int:
    a, b = map(int, score.split(":"))
    return a + b


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT m.id, m.competition_slug, m.team_a, m.team_b, m.result_a, m.result_b,
               m.match_time, m.matchday,
               p.best_score, p.win_rate, p.draw_rate, p.lose_rate, p.confidence, p.model_used,
               o.win_win, o.draw, o.win_lose,
               CASE WHEN o.score_odds IS NULL OR o.score_odds='' THEN 0 ELSE 1 END AS has_crs
        FROM matches m
        JOIN predictions p ON p.match_id = m.id
        LEFT JOIN odds o ON o.match_id = m.id
        WHERE m.competition_slug IN (?,?,?,?,?)
          AND m.season = '2026/27'
          AND m.result_a IS NOT NULL AND m.result_b IS NOT NULL
          AND p.best_score IS NOT NULL AND p.best_score != ''
        ORDER BY m.match_time DESC
        """,
        SLUGS,
    ).fetchall()

    # dedupe by match_id keep first (already ordered? join may duplicate odds)
    seen = set()
    matches = []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        matches.append(r)

    by_lg = defaultdict(list)
    overall = Counter()
    pred_primary = Counter()
    actual_c = Counter()
    miss_bucket = Counter()
    wdl_confusion = Counter()
    draw_rate_bins = Counter()
    template = Counter()
    samples_miss = []
    samples_hit = []

    for r in matches:
        actual = f"{r['result_a']}:{r['result_b']}"
        p1, p2, upset = _parse_best(r["best_score"])
        if not p1:
            continue
        overall["n"] += 1
        actual_c[actual] += 1
        pred_primary[p1] += 1
        hit_p = actual == p1
        hit_any = actual in {p1, p2, upset}
        if hit_p:
            overall["primary"] += 1
        if hit_any:
            overall["any3"] += 1

        aw = _wdl(actual)
        pw = _wdl(p1)
        wdl_ok = aw == pw
        if wdl_ok:
            overall["wdl_ok"] += 1
        else:
            overall["wdl_miss"] += 1
            wdl_confusion[f"{pw}->{aw}"] += 1

        # template clustering
        template[f"{p1}|{p2}|{upset}"] += 1

        # draw_rate pattern
        dr = float(r["draw_rate"] or 0)
        if dr >= 40:
            draw_rate_bins["dr>=40"] += 1
        elif dr <= 20:
            draw_rate_bins["dr<=20"] += 1
        else:
            draw_rate_bins["dr_mid"] += 1

        if not hit_p:
            if not wdl_ok:
                miss_bucket["1_wdl_wrong"] += 1
            elif _goals(actual) - _goals(p1) >= 2:
                miss_bucket["2_under_goals"] += 1
            elif _goals(p1) - _goals(actual) >= 2:
                miss_bucket["3_over_goals"] += 1
            elif abs(r["result_a"] - int(p1.split(":")[0])) + abs(
                r["result_b"] - int(p1.split(":")[1])
            ) == 1:
                miss_bucket["4_off_by_1"] += 1
            else:
                miss_bucket["5_other_same_wdl"] += 1

            if len(samples_miss) < 40:
                samples_miss.append(
                    {
                        "lg": r["competition_slug"],
                        "md": r["matchday"],
                        "match": f"{r['team_a']} vs {r['team_b']}",
                        "actual": actual,
                        "picks": [p1, p2, upset],
                        "wdl": f"{pw}->{aw}",
                        "rates": [r["win_rate"], r["draw_rate"], r["lose_rate"]],
                        "has_euro": r["win_win"] is not None,
                        "has_crs": bool(r["has_crs"]),
                        "any3": hit_any,
                    }
                )
        else:
            if len(samples_hit) < 15:
                samples_hit.append(
                    {
                        "lg": r["competition_slug"],
                        "match": f"{r['team_a']} vs {r['team_b']}",
                        "actual": actual,
                        "picks": [p1, p2, upset],
                    }
                )

        by_lg[r["competition_slug"]].append(
            {
                "hit_p": hit_p,
                "hit_any": hit_any,
                "wdl_ok": wdl_ok,
                "has_euro": r["win_win"] is not None,
                "has_crs": bool(r["has_crs"]),
                "p1": p1,
                "actual": actual,
                "dr": dr,
            }
        )

    # odds coverage among predicted
    with_euro = sum(1 for r in matches if r["win_win"] is not None)
    with_crs = sum(1 for r in matches if r["has_crs"])

    league_summary = {}
    for slug, items in by_lg.items():
        n = len(items)
        league_summary[slug] = {
            "n": n,
            "primary": sum(1 for x in items if x["hit_p"]),
            "any3": sum(1 for x in items if x["hit_any"]),
            "wdl_ok": sum(1 for x in items if x["wdl_ok"]),
            "with_euro": sum(1 for x in items if x["has_euro"]),
            "with_crs": sum(1 for x in items if x["has_crs"]),
            "primary_pct": round(sum(1 for x in items if x["hit_p"]) / n, 3) if n else None,
            "any3_pct": round(sum(1 for x in items if x["hit_any"]) / n, 3) if n else None,
            "wdl_pct": round(sum(1 for x in items if x["wdl_ok"]) / n, 3) if n else None,
            "top_primary": Counter(x["p1"] for x in items).most_common(5),
        }

    n = overall["n"] or 1
    out = {
        "n": overall["n"],
        "primary_hits": overall["primary"],
        "any3_hits": overall["any3"],
        "wdl_ok": overall["wdl_ok"],
        "primary_pct": round(overall["primary"] / n, 3),
        "any3_pct": round(overall["any3"] / n, 3),
        "wdl_pct": round(overall["wdl_ok"] / n, 3),
        "with_euro": with_euro,
        "with_crs": with_crs,
        "euro_pct": round(with_euro / n, 3),
        "crs_pct": round(with_crs / n, 3),
        "miss_bucket": dict(miss_bucket),
        "wdl_confusion": dict(wdl_confusion.most_common(10)),
        "draw_rate_bins": dict(draw_rate_bins),
        "top_pred_primary": pred_primary.most_common(10),
        "top_actual": actual_c.most_common(10),
        "top_templates": template.most_common(8),
        "leagues": league_summary,
        "samples_miss": samples_miss,
        "samples_hit": samples_hit,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k not in ("samples_miss", "samples_hit")}, ensure_ascii=False, indent=2))
    print("\n--- miss samples (first 20) ---")
    for s in samples_miss[:20]:
        print(s)


if __name__ == "__main__":
    main()
