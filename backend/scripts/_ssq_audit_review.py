# -*- coding: utf-8 -*-
"""Audit SSQ algorithm: recent hits + structural health + quick backtest."""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from service.digital_pick import period_seed
from service.ssq_service import analyze_ssq, build_ssq_recommendations, fetch_ssq_history


async def main() -> None:
    draws = await fetch_ssq_history(100, force_refresh=True)
    print("=== LATEST DRAWS ===")
    for d in draws[:6]:
        print(d["issue"], d["result"], "sum", sum(d["red"]))

    store = _BACKEND / "data" / "digital_rec_history.json"
    data = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    print("\n=== STORED vs NEXT ===")
    for based in sorted(k.split(":", 1)[1] for k in data if k.startswith("ssq:"))[-5:]:
        later = [d for d in draws if str(d["issue"]) > based]
        if not later:
            continue
        nxt = min(later, key=lambda x: str(x["issue"]))
        ar, ab = set(nxt["red"]), nxt["blue"]
        picks = data.get(f"ssq:{based}", {}).get("picks") or []
        if not picks:
            continue
        best = 0
        any_b = False
        sets = []
        blues = []
        for p in picks:
            dig = [int(x) for x in p["digits"]]
            reds = set(dig[:6])
            blue = dig[6]
            best = max(best, len(reds & ar))
            any_b = any_b or blue == ab
            sets.append(reds)
            blues.append(blue)
        ov = [len(sets[i] & sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))]
        print(
            f"based {based} -> {nxt['issue']} {nxt['result']} | "
            f"max_red={best} any_blue={any_b} blues={blues} "
            f"max_ov={max(ov) if ov else 0} cover={len(set().union(*sets)) if sets else 0}"
        )

    print("\n=== CURRENT BUILDER STRUCTURE (based on latest) ===")
    hist = draws[1:] if draws else []
    analysis = analyze_ssq(hist[:80])
    seed = period_seed(str(hist[0]["issue"]), 0)
    recs = build_ssq_recommendations(analysis, seed=seed)
    singles = [r for r in recs if r["mode"] == "ssq"]
    sets = [set(r["red"]) for r in singles]
    print("modes", [r["mode"] for r in recs])
    print("singles_overlap", [len(sets[i] & sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))])
    print("union_cover", len(set().union(*sets)) if sets else 0)
    print("blues", [r.get("blue") for r in recs])
    print("hot", analysis["hot_digits"], "sum_band", analysis["sum_stats"]["target_lo"], analysis["sum_stats"]["target_hi"])

    # walk-forward 40 periods quick
    print("\n=== QUICK BACKTEST 40 periods ===")
    n_eval = 40
    window = 40
    model_best = []
    model_blue = []
    rand_best = []
    rand_blue = []
    overlaps = []
    covers = []
    rng = random.Random(42)
    for i in range(n_eval):
        target = draws[i]
        hist_i = draws[i + 1 : i + 1 + window]
        if len(hist_i) < window:
            break
        a = analyze_ssq(hist_i)
        seed = period_seed(str(hist_i[0]["issue"]), 0)
        recs = build_ssq_recommendations(a, seed=seed)
        ar, ab = set(target["red"]), target["blue"]
        best = 0
        any_b = False
        ssets = []
        for r in recs:
            if r.get("mode") == "fushi":
                reds = set(r.get("red") or [])
            elif r.get("mode") == "dantuo":
                reds = set(r.get("dan") or []) | set(r.get("tuo") or [])
            else:
                reds = set(r.get("red") or (r.get("digits") or [])[:6])
            blue = r.get("blue")
            if r.get("mode") == "ssq":
                ssets.append(reds)
                best = max(best, len(reds & ar))
            elif r.get("mode") == "fushi":
                best = max(best, len(reds & ar))  # pool hits as soft
            any_b = any_b or (blue == ab)
        model_best.append(best)
        model_blue.append(1 if any_b else 0)
        if len(ssets) >= 2:
            overlaps.append(max(len(ssets[x] & ssets[y]) for x in range(len(ssets)) for y in range(x + 1, len(ssets))))
            covers.append(len(set().union(*ssets)))
        # random 5 singles
        rb = 0
        rany = False
        for _ in range(5):
            rr = set(rng.sample(range(1, 34), 6))
            bb = rng.randint(1, 16)
            rb = max(rb, len(rr & ar))
            rany = rany or bb == ab
        rand_best.append(rb)
        rand_blue.append(1 if rany else 0)

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print(f"model avg_best_red={avg(model_best):.3f} any_blue={avg(model_blue):.3f} n={len(model_best)}")
    print(f"random avg_best_red={avg(rand_best):.3f} any_blue={avg(rand_blue):.3f}")
    print(f"delta red={avg(model_best)-avg(rand_best):+.3f} blue={avg(model_blue)-avg(rand_blue):+.3f}")
    print(f"struct avg_max_overlap={avg(overlaps):.2f} avg_union_cover={avg(covers):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
