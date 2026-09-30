# -*- coding: utf-8 -*-
"""Review stored SSQ picks vs recent actual draws."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from service.ssq_service import fetch_ssq_history  # noqa: E402


async def main() -> None:
    draws = await fetch_ssq_history(30)
    data = json.loads((_BACKEND / "data" / "digital_rec_history.json").read_text(encoding="utf-8"))
    by_issue = {str(d["issue"]): d for d in draws}

    print("=== Tonight / recent actual ===")
    for d in draws[:3]:
        print(d["issue"], d["result"], "sum", sum(d["red"]))

    print("\n=== Stored prediction vs next draw ===")
    for based in ["2026101", "2026102", "2026103"]:
        stored = data.get(f"ssq:{based}")
        # next issue after based among known draws
        later = [d for d in draws if str(d["issue"]) > based]
        if not stored or not later:
            print(based, "missing")
            continue
        nxt = min(later, key=lambda x: str(x["issue"]))
        ar, ab = set(nxt["red"]), nxt["blue"]
        picks = stored.get("picks") or []
        best = 0
        any_b = False
        blues = []
        sets = []
        for p in picks:
            dig = [int(x) for x in p["digits"]]
            reds = set(dig[:6])
            blue = dig[6]
            best = max(best, len(reds & ar))
            any_b = any_b or (blue == ab)
            blues.append(blue)
            sets.append(reds)
        ov = [len(sets[i] & sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))]
        print(
            f"based_on {based} -> {nxt['issue']} {nxt['result']} | "
            f"max_red={best} any_blue={any_b} blues={blues} "
            f"max_pair_overlap={max(ov) if ov else 0}"
        )
        for i, p in enumerate(picks):
            dig = [int(x) for x in p["digits"]]
            reds = set(dig[:6])
            print(f"  pick{i+1} {dig} hits={sorted(reds & ar)} blue_ok={dig[6]==ab}")


if __name__ == "__main__":
    asyncio.run(main())
