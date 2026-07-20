# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect("worldcup2026.db")
conn.text_factory = str
c = conn.cursor()
c.execute(
    """
    SELECT stage, team_a, team_b, match_time, COUNT(*) n
    FROM matches WHERE competition_slug='worldcup-2026'
      AND stage NOT IN ('小组赛', '')
    GROUP BY stage, team_a, team_b, match_time
    ORDER BY stage, team_a
    """
)
rows = c.fetchall()
print("knockout rows:", len(rows))
for r in rows:
    print(r)
c.execute(
    """
    SELECT stage, COUNT(*) FROM matches
    WHERE competition_slug='worldcup-2026' AND stage != '小组赛'
    GROUP BY stage
    """
)
print("by stage:", c.fetchall())
c.execute("SELECT DISTINCT stage FROM matches WHERE competition_slug='worldcup-2026'")
print("all stages:", c.fetchall())
conn.close()
