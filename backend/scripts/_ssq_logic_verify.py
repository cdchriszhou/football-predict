# -*- coding: utf-8 -*-
"""综合核查：开奖 vs 推荐 + 结构健康 + 随机基线。"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from service.digital_pick import period_seed  # noqa: E402
from service.ssq_service import (  # noqa: E402
    _ticket_shape_ok,
    analyze_ssq,
    build_ssq_recommendations,
    fetch_ssq_history,
)


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


async def main() -> None:
    draws = await fetch_ssq_history(100, force_refresh=True)
    print("draws", len(draws), "newest", draws[0]["issue"], "oldest", draws[-1]["issue"])

    sums, odds, runs = [], [], []
    highb = 0
    zone_ok = 0
    for d in draws:
        r = sorted(d["red"])
        b = int(d["blue"])
        sums.append(sum(r))
        odds.append(sum(1 for x in r if x % 2))
        mr, cur = 1, 1
        for i in range(1, 6):
            if r[i] == r[i - 1] + 1:
                cur += 1
                mr = max(mr, cur)
            else:
                cur = 1
        runs.append(mr)
        if b > 10:
            highb += 1
        z = [
            sum(1 for x in r if 1 <= x <= 11),
            sum(1 for x in r if 12 <= x <= 22),
            sum(1 for x in r if 23 <= x <= 33),
        ]
        if min(z) > 0:
            zone_ok += 1
    print("\n=== ACTUAL DIST ===")
    print(
        "sum mean/p10/p90",
        round(sum(sums) / len(sums), 1),
        sorted(sums)[9],
        sorted(sums)[89],
    )
    print("odd dist", dict(Counter(odds)))
    print("max_run dist", dict(Counter(runs)))
    print("blue high>10 rate", round(highb / len(draws), 3))
    print("zone all-nonzero rate", round(zone_ok / len(draws), 3))

    n_eval, window = 50, 40
    model_best, rand_best = [], []
    mb, rb = [], []
    primary_hits, fushi_hits, dan_full = [], [], []
    struct, shape_ok_rate, sum_in_band, blue_unique = [], [], [], []
    smells: Counter = Counter()
    details = []
    rng = random.Random(42)

    for i in range(min(n_eval, len(draws) - window)):
        t = draws[i]
        hist = draws[i + 1 : i + 1 + window]
        ar = set(t["red"])
        ab = int(t["blue"])
        a = analyze_ssq(hist)
        seed = period_seed(str(hist[0]["issue"]), 0)
        excl: set[tuple[int, ...]] = set()
        if hist[0].get("digits"):
            excl.add(tuple(int(x) for x in hist[0]["digits"][:7]))
        recs = build_ssq_recommendations(a, seed=seed, exclude=excl)
        singles = [r for r in recs if r["mode"] == "ssq"]
        fushi = next(r for r in recs if r["mode"] == "fushi")
        dantuo = next(r for r in recs if r["mode"] == "dantuo")

        sbest = max(len(set(r["red"]) & ar) for r in singles)
        fhit = len(set(fushi["red"]) & ar)
        dfull = set(dantuo["dan"]).issubset(ar)
        model_best.append(sbest)
        any_blue = (
            any(int(r["blue"]) == ab for r in singles)
            or int(fushi["blue"]) == ab
            or int(dantuo["blue"]) == ab
        )
        mb.append(any_blue)
        primary_hits.append(len(set(singles[0]["red"]) & ar))
        fushi_hits.append(fhit)
        dan_full.append(1 if dfull else 0)

        sets = [set(r["red"]) for r in singles]
        ov = max(
            len(sets[x] & sets[y])
            for x in range(len(sets))
            for y in range(x + 1, len(sets))
        )
        cover = len(set().union(*sets))
        struct.append((ov, cover))
        shape_ok_rate.append(
            sum(1 for r in singles if _ticket_shape_ok(r["red"])) / len(singles)
        )
        ss = a["sum_stats"]
        lo, hi = ss["target_lo"], ss["target_hi"]
        sum_in_band.append(
            sum(1 for r in singles if lo <= sum(r["red"]) <= hi) / len(singles)
        )
        blues_s = [int(r["blue"]) for r in singles]
        blue_unique.append(len(set(blues_s)) == len(blues_s))

        # structural smells
        if len(set(blues_s)) < len(blues_s):
            smells["dup_blue"] += 1
        if sum(1 for b in blues_s if b > 10) > 1:
            smells["too_many_high_blue"] += 1
        if any(
            len(sets[x] & sets[y]) >= 4
            for x in range(len(sets))
            for y in range(x + 1, len(sets))
        ):
            smells["overlap_ge4"] += 1
        if len(fushi["red"]) != 7:
            smells["fushi_ne7"] += 1
        if not set(singles[0]["red"]).issubset(set(fushi["red"])):
            smells["fushi_not_anchor"] += 1
        if int(fushi["blue"]) != int(singles[0]["blue"]):
            smells["fushi_blue_mismatch"] += 1
        if not set(dantuo["dan"]).issubset(set(singles[0]["red"])):
            smells["dan_not_from_primary"] += 1
        if len(dantuo["dan"]) != 2 or len(dantuo["tuo"]) != 5:
            smells["dantuo_struct"] += 1

        rbest, rany = 0, False
        for _ in range(3):
            rr = set(rng.sample(range(1, 34), 6))
            bb = rng.randint(1, 16)
            rbest = max(rbest, len(rr & ar))
            rany = rany or bb == ab
        rand_best.append(rbest)
        rb.append(rany)

        if i < 12:
            details.append(
                {
                    "issue": t["issue"],
                    "actual": t["result"],
                    "primary": singles[0]["display"],
                    "p_hit": primary_hits[-1],
                    "best": sbest,
                    "fushi": fhit,
                    "dan_ok": bool(dfull),
                    "any_b": any_blue,
                    "ov": ov,
                    "cover": cover,
                    "blues": blues_s + [int(fushi["blue"]), int(dantuo["blue"])],
                }
            )

    print("\n=== WALKFORWARD 50 (3 singles + fushi + dantuo) ===")
    print(
        "model avg best_red(singles)",
        round(_avg(model_best), 3),
        "any_blue",
        round(_avg(mb), 3),
    )
    print(
        "random3 avg best_red",
        round(_avg(rand_best), 3),
        "any_blue",
        round(_avg(rb), 3),
    )
    print(
        "delta red",
        round(_avg(model_best) - _avg(rand_best), 3),
        "blue",
        round(_avg(mb) - _avg(rb), 3),
    )
    print("primary avg hit", round(_avg(primary_hits), 3))
    print(
        "fushi avg pool hit",
        round(_avg(fushi_hits), 3),
        "dan_all_hit_rate",
        round(_avg(dan_full), 3),
    )
    print(
        "struct avg max_ov",
        round(_avg([x[0] for x in struct]), 2),
        "avg cover",
        round(_avg([x[1] for x in struct]), 2),
    )
    print(
        "shape_ok",
        round(_avg(shape_ok_rate), 3),
        "sum_in_band",
        round(_avg(sum_in_band), 3),
        "blue_unique",
        round(_avg([1 if x else 0 for x in blue_unique]), 3),
    )
    print("best_red dist", dict(Counter(model_best)))
    print("primary hit dist", dict(Counter(primary_hits)))
    print("STRUCTURAL SMELLS", dict(smells))

    print("\n=== RECENT 12 RETRO DETAIL ===")
    for d in details:
        print(
            f"{d['issue']} {d['actual']} | primary={d['primary']} "
            f"hit={d['p_hit']} best={d['best']} fushi={d['fushi']} "
            f"dan={d['dan_ok']} blue={d['any_b']} ov={d['ov']} "
            f"cover={d['cover']} blues={d['blues']}"
        )

    store = _BACKEND / "data" / "digital_rec_history.json"
    data = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    ssq_keys = sorted(k for k in data if k.startswith("ssq:"))
    print("\n=== STORED vs NEXT ===")
    for k in ssq_keys:
        based = k.split(":", 1)[1]
        later = [d for d in draws if str(d["issue"]) > based]
        if not later:
            print(based, "no next yet / forward only")
            picks = data[k].get("picks") or []
            print("  picks", len(picks), [p.get("display") or p.get("digits") for p in picks])
            continue
        nxt = min(later, key=lambda x: str(x["issue"]))
        ar = set(nxt["red"])
        ab = int(nxt["blue"])
        picks = data[k].get("picks") or []
        parts = []
        best = 0
        anyb = False
        sets = []
        for p in picks:
            dig = [int(x) for x in (p.get("digits") or [])]
            mode = p.get("mode") or "ssq"
            if mode == "fushi":
                reds = {int(x) for x in (p.get("red") or dig[:7])}
            elif mode == "dantuo":
                reds = {int(x) for x in (p.get("dan") or [])} | {
                    int(x) for x in (p.get("tuo") or [])
                }
            else:
                reds = set(dig[:6]) if len(dig) >= 6 else set()
            blue = p.get("blue")
            if blue is None and len(dig) > 6:
                blue = dig[6]
            h = len(reds & ar)
            best = max(best, h)
            bh = blue == ab
            anyb = anyb or bh
            if mode == "ssq" and reds:
                sets.append(reds)
            tag = "B" if bh else ""
            parts.append(f"{mode}:{h}{tag}")
        ov = max(
            (
                len(sets[i] & sets[j])
                for i in range(len(sets))
                for j in range(i + 1, len(sets))
            ),
            default=0,
        )
        cover = len(set().union(*sets)) if sets else 0
        print(
            f"based {based}->{nxt['issue']} {nxt['result']} "
            f"max_red={best} blue={anyb} ov={ov} cover={cover} | "
            + ", ".join(parts)
        )


if __name__ == "__main__":
    asyncio.run(main())
