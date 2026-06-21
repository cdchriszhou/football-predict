# -*- coding: utf-8 -*-
import sqlite3

from crawler.schedule_crawler import _build_expected_matches, _match_key

conn = sqlite3.connect("worldcup2026.db")
conn.text_factory = str
c = conn.cursor()
expected = _build_expected_matches()
exp_keys = {_match_key(m["stage"], m["group_name"], m["team_a"], m["team_b"]) for m in expected}
c.execute(
    "SELECT stage, group_name, team_a, team_b FROM matches WHERE competition_slug=?",
    ("worldcup-2026",),
)
db_keys = set()
for r in c.fetchall():
    db_keys.add(r)
missing = exp_keys - db_keys
extra = db_keys - exp_keys
print("missing from DB:", len(missing))
for k in sorted(missing)[:20]:
    print(" ", k)
print("extra keys in DB:", len(extra))
for k in sorted(extra)[:10]:
    print(" ", k)
conn.close()
