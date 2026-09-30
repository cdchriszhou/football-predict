# -*- coding: utf-8 -*-
"""度量复式与主推单式的覆盖相关性。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from service.digital_pick import period_seed  # noqa: E402
from service.ssq_service import analyze_ssq, build_ssq_recommendations, fetch_ssq_history  # noqa: E402


def avg(xs: list[float]) -> float:
    return round(sum(xs) / max(1, len(xs)), 3)


async def main() -> None:
    draws = await fetch_ssq_history(60)
    n = 40
    fushi_hits: list[int] = []
    dan_hits: list[int] = []
    single_best: list[int] = []
    fushi_vs_s1: list[int] = []
    captured: list[float] = []

    for i in range(n):
        target = draws[i]
        prior = draws[i + 1 : i + 1 + 50]
        if len(prior) < 30:
            break
        a = analyze_ssq(prior)
        seed = period_seed(str(prior[0]["issue"]), 0)
        ex = {tuple(int(x) for x in prior[0]["digits"][:7])}
        recs = build_ssq_recommendations(a, seed=seed, exclude=ex)
        ar = set(target["red"])
        singles = [r for r in recs if r["mode"] == "ssq"]
        fushi = next(r for r in recs if r["mode"] == "fushi")
        dantuo = next(r for r in recs if r["mode"] == "dantuo")
        sb = max(len(set(r["digits"][:6]) & ar) for r in singles)
        single_best.append(sb)
        fh = len(set(fushi["red"]) & ar)
        fushi_hits.append(fh)
        dh = len((set(dantuo["dan"]) | set(dantuo["tuo"])) & ar)
        dan_hits.append(dh)
        s1 = set(singles[0]["digits"][:6])
        ov = len(s1 & set(fushi["red"]))
        fushi_vs_s1.append(ov)
        hit = s1 & ar
        if len(hit) >= 3:
            captured.append(len(hit & set(fushi["red"])) / len(hit))

    print("n", len(single_best))
    print("avg single_best", avg(single_best), "pct>=3", avg([1 if x >= 3 else 0 for x in single_best]))
    print(
        "avg fushi_pool_hits", avg(fushi_hits),
        "pct>=3", avg([1 if x >= 3 else 0 for x in fushi_hits]),
        "pct0", avg([1 if x == 0 else 0 for x in fushi_hits]),
    )
    print("avg dantuo_pool_hits", avg(dan_hits), "pct>=3", avg([1 if x >= 3 else 0 for x in dan_hits]))
    print(
        "avg overlap(fushi,s1)", avg(fushi_vs_s1),
        "pct<=1", avg([1 if x <= 1 else 0 for x in fushi_vs_s1]),
        "pct>=4", avg([1 if x >= 4 else 0 for x in fushi_vs_s1]),
    )
    print(
        "when s1>=3 hits, fraction of those hits also in fushi: avg",
        avg(captured) if captured else None,
        "n",
        len(captured),
    )


if __name__ == "__main__":
    asyncio.run(main())
