# -*- coding: utf-8 -*-
import sqlite3

from crawler.schedule_crawler import _build_expected_matches, _match_key

conn = sqlite3.connect("worldcup2026.db")
conn.text_factory = str
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM matches WHERE competition_slug=?", ("worldcup-2026",))
total = c.fetchone()[0]
expected = _build_expected_matches()
print("canonical expected:", len(expected))
c.execute(
    """
    SELECT stage, group_name, team_a, team_b, match_time, COUNT(*) n
    FROM matches WHERE competition_slug=?
    GROUP BY stage, group_name, team_a, team_b, match_time
    """,
    ("worldcup-2026",),
)
groups = c.fetchall()
print("unique fixture keys (with time):", len(groups))
print("total rows:", total)
extra = sum(r[5] - 1 for r in groups if r[5] > 1)
print("duplicate rows to remove:", extra)
print("would remain after dedupe:", total - extra)
c.execute(
    """
    SELECT stage, group_name, team_a, team_b, COUNT(*) n
    FROM matches WHERE competition_slug=?
    GROUP BY stage, group_name, team_a, team_b
    HAVING n > 1
    ORDER BY n DESC LIMIT 10
    """,
    ("worldcup-2026",),
)
print("dup by team key (no time):", c.fetchall()[:5])
conn.close()
