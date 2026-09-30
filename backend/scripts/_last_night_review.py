# -*- coding: utf-8 -*-
"""Dump last-night Big Five matches as UTF-8 JSON."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "worldcup2026.db"
OUT = Path(__file__).resolve().parent / "_last_night_dump.json"
SLUGS = ("premier-league", "la-liga", "serie-a", "bundesliga", "ligue-1")


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    finished = [
        dict(r)
        for r in con.execute(
            """
            SELECT competition_slug, season, COUNT(*) n,
                   MIN(match_time) mn, MAX(match_time) mx
            FROM matches
            WHERE competition_slug IN (?,?,?,?,?)
              AND result_a IS NOT NULL AND result_b IS NOT NULL
            GROUP BY competition_slug, season
            """,
            SLUGS,
        )
    ]

    window = [
        dict(r)
        for r in con.execute(
            """
            SELECT m.id, m.competition_slug, m.season, m.matchday, m.stage,
                   m.match_time, m.team_a, m.team_b, m.result_a, m.result_b,
                   m.status, m.location,
                   p.best_score, p.win_rate, p.draw_rate, p.lose_rate,
                   p.confidence, p.model_used,
                   o.win_win, o.draw AS euro_draw, o.win_lose, o.handicap,
                   o.score_odds, o.source AS odds_source
            FROM matches m
            LEFT JOIN predictions p ON p.match_id = m.id
            LEFT JOIN odds o ON o.match_id = m.id
            WHERE m.competition_slug IN (?,?,?,?,?)
              AND m.season = '2026/27'
              AND m.match_time >= '2026-08-25 12:00:00'
              AND m.match_time < '2026-08-26 12:00:00'
            ORDER BY m.match_time ASC, m.id ASC
            """,
            SLUGS,
        )
    ]

    # Monday-night cluster (Aug 25 00:00-06:00 China = Aug 24 evening Europe)
    mon_night = [
        dict(r)
        for r in con.execute(
            """
            SELECT m.id, m.competition_slug, m.matchday, m.match_time,
                   m.team_a, m.team_b, m.result_a, m.result_b, m.status,
                   p.best_score, p.win_rate, p.draw_rate, p.lose_rate,
                   o.win_win, o.draw AS euro_draw, o.win_lose, o.handicap,
                   CASE WHEN o.score_odds IS NULL OR o.score_odds='' THEN 0 ELSE 1 END AS has_crs
            FROM matches m
            LEFT JOIN predictions p ON p.match_id = m.id
            LEFT JOIN odds o ON o.match_id = m.id
            WHERE m.competition_slug IN (?,?,?,?,?)
              AND m.season = '2026/27'
              AND m.match_time >= '2026-08-25 00:00:00'
              AND m.match_time < '2026-08-25 12:00:00'
            ORDER BY m.match_time ASC, m.id ASC
            """,
            SLUGS,
        )
    ]

    upcoming = [
        dict(r)
        for r in con.execute(
            """
            SELECT m.id, m.competition_slug, m.matchday, m.match_time,
                   m.team_a, m.team_b, m.result_a, m.result_b, m.status
            FROM matches m
            WHERE m.competition_slug IN (?,?,?,?,?)
              AND m.season = '2026/27'
              AND m.match_time >= '2026-08-26 12:00:00'
              AND m.match_time < '2026-08-28 00:00:00'
            ORDER BY m.match_time ASC
            """,
            SLUGS,
        )
    ]

    no_result_recent = [
        dict(r)
        for r in con.execute(
            """
            SELECT m.id, m.competition_slug, m.matchday, m.match_time,
                   m.team_a, m.team_b, m.status, m.result_a, m.result_b
            FROM matches m
            WHERE m.competition_slug IN (?,?,?,?,?)
              AND m.season = '2026/27'
              AND m.match_time >= '2026-08-24'
              AND m.match_time < '2026-08-27'
              AND (m.result_a IS NULL OR m.status NOT IN ('finished','FT','完场'))
            ORDER BY m.match_time
            """,
            SLUGS,
        )
    ]

    OUT.write_text(
        json.dumps(
            {
                "finished_by_league": finished,
                "last_night_window_aug25_12_to_aug26_12": window,
                "mon_night_aug25_am": mon_night,
                "upcoming_to_aug28": upcoming,
                "recent_no_result": no_result_recent,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print("wrote", OUT, "window", len(window), "mon", len(mon_night), "upcoming", len(upcoming))


if __name__ == "__main__":
    main()
