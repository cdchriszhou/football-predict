# -*- coding: utf-8 -*-
import asyncio
import sys

sys.path.insert(0, ".")
from service.digital_pick import period_seed
from service.ssq_service import (
    _BLUE_LOW_MAX,
    analyze_ssq,
    build_ssq_recommendations,
    fetch_ssq_history,
)


async def main() -> None:
    draws = await fetch_ssq_history(80, force_refresh=True)
    print("latest", draws[0]["issue"], draws[0]["result"])
    for i in range(6):
        t = draws[i]
        hist = draws[i + 1 :]
        a = analyze_ssq(hist[:80])
        seed = period_seed(str(hist[0]["issue"]), 0)
        recs = build_ssq_recommendations(a, seed=seed)
        singles = [r for r in recs if r["mode"] == "ssq"]
        blues = [r["blue"] for r in singles]
        high = sum(1 for b in blues if b > _BLUE_LOW_MAX)
        ar = set(t["red"])
        ab = t["blue"]
        best = max(len(set(r["red"]) & ar) for r in singles)
        anyb = any(int(r.get("blue") or -1) == ab for r in recs)
        print(
            t["issue"],
            t["result"],
            "blues=",
            blues,
            "high_n=",
            high,
            "best_red=",
            best,
            "any_blue=",
            anyb,
        )


if __name__ == "__main__":
    asyncio.run(main())
