# -*- coding: utf-8 -*-
"""Review score predictions vs actual results for recently finished matches."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from data.worldcup_history import HISTORICAL_MATCHES
from crawler.team_crawler import TEAM_DATA
from service.score_pick import score_matches_pick

BJ = timezone(timedelta(hours=8))


def _load_prediction(cur, match_id: int) -> dict | None:
    cur.execute(
        """
        SELECT win_rate, draw_rate, lose_rate, best_score, reason
        FROM predictions WHERE match_id=? ORDER BY id DESC LIMIT 1
        """,
        (match_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    wr, dr, lr, best_score, reason = row
    picks = []
    upset = None
    if best_score:
        try:
            blob = json.loads(best_score)
            if isinstance(blob, dict):
                picks = list(blob.get("best_scores") or blob.get("likely") or [])
                upset = blob.get("upset_score") or blob.get("upset")
            elif isinstance(blob, list):
                picks = blob
        except (json.JSONDecodeError, TypeError):
            picks = [best_score] if best_score else []
    if reason and isinstance(reason, str):
        try:
            meta = json.loads(reason)
            if isinstance(meta, dict):
                extra = meta.get("score_picks") or meta.get("likely_scores")
                if isinstance(extra, dict):
                    picks = picks or list(extra.get("best_scores") or [])
                    upset = upset or extra.get("upset_score")
                elif isinstance(extra, list) and not picks:
                    picks = extra
                upset = upset or meta.get("upset_score")
        except (json.JSONDecodeError, TypeError):
            pass
    return {"picks": picks, "upset": upset, "wdl": (wr, dr, lr)}


def _crs_from_db(cur, match_id: int) -> dict:
    cur.execute("SELECT score_odds FROM odds WHERE match_id=?", (match_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        return {}
    raw = json.loads(row[0])
    raw.pop("_meta", None)
    return raw


def main():
    conn = sqlite3.connect("worldcup2026.db")
    conn.text_factory = str
    cur = conn.cursor()

    now_bj = datetime.now(BJ)
    # 今天凌晨 00:00（北京时间）起
    window_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        SELECT id, team_a, team_b, match_time, result_a, result_b
        FROM matches
        WHERE competition_slug='worldcup-2026'
          AND status='finished'
          AND result_a IS NOT NULL
          AND match_time >= ?
        ORDER BY match_time
        """,
        (start_str,),
    )
    rows = cur.fetchall()

    if not rows:
        # fallback: last 48h finished
        fallback = (now_bj - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            SELECT id, team_a, team_b, match_time, result_a, result_b
            FROM matches
            WHERE competition_slug='worldcup-2026'
              AND status='finished'
              AND result_a IS NOT NULL
              AND match_time >= ?
            ORDER BY match_time
            """,
            (fallback,),
        )
        rows = cur.fetchall()
        print(f"(无今日完赛，回退至 48h 内: >= {fallback})\n")

    # Also merge history entries not yet in DB window
    hist_new = [
        m for m in HISTORICAL_MATCHES
        if m.get("year") == 2026 and m.get("result_a") is not None
    ]

    print(f"北京时间窗口起点: {start_str}  当前: {now_bj.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'比赛':<24} {'时间':<18} {'实际':<6} {'首推':<6} {'次推':<6} {'冷门':<8} 命中")
    print("-" * 82)

    seen = set()
    primary_hits = triple_hits = total = 0

    def report(ta, tb, mt, ra, rb, pred, crs):
        nonlocal primary_hits, triple_hits, total
        actual = f"{ra}:{rb}"
        picks = list(pred.get("picks") or []) if pred else []
        upset = (pred or {}).get("upset")
        p1 = picks[0] if picks else "?"
        p2 = picks[1] if len(picks) > 1 else "-"
        pu = upset or "-"
        all_p = picks + ([upset] if upset else [])
        ph = score_matches_pick(actual, p1, crs)
        th = any(score_matches_pick(actual, p, crs) for p in all_p if p)
        total += 1
        primary_hits += int(ph)
        triple_hits += int(th)
        mark = "✅首推" if ph else ("✅三选" if th else "❌")
        mt_short = (mt or "")[:16]
        print(f"{ta+' vs '+tb:<24} {mt_short:<18} {actual:<6} {p1:<6} {p2:<6} {pu:<8} {mark}")

    for mid, ta, tb, mt, ra, rb in rows:
        key = (ta, tb)
        seen.add(key)
        pred = _load_prediction(cur, mid)
        crs = _crs_from_db(cur, mid)
        report(ta, tb, mt, ra, rb, pred, crs)

    for m in hist_new:
        key = (m["team_a"], m["team_b"])
        if key in seen:
            continue
        # only show if likely recent (matchday 1 june games) - skip if we already have DB
        pred = None
        crs = m.get("score_odds") or {}
        report(m["team_a"], m["team_b"], "history", m["result_a"], m["result_b"], pred, crs)

    conn.close()
    if total:
        print("-" * 82)
        print(f"首推 {primary_hits}/{total}  三选 {triple_hits}/{total}")


if __name__ == "__main__":
    main()
