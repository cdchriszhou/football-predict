# -*- coding: utf-8 -*-
"""对照今晚双色球开奖，审查推荐结构与逻辑问题。"""
from __future__ import annotations

import asyncio
import json
import sys
from itertools import combinations
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from service.digital_pick import period_seed  # noqa: E402
from service.digital_rec_store import _pick_from_rec, get_stored_picks  # noqa: E402
from service.ssq_service import (  # noqa: E402
    analyze_ssq,
    build_ssq_recommendations,
    fetch_ssq_history,
)


def morph(reds) -> dict:
    s = sorted(int(x) for x in reds)
    runs: list[list[int]] = []
    cur = [s[0]]
    for x in s[1:]:
        if x == cur[-1] + 1:
            cur.append(x)
        else:
            runs.append(cur)
            cur = [x]
    runs.append(cur)
    return {
        "sum": sum(s),
        "odd": sum(1 for x in s if x % 2),
        "even": sum(1 for x in s if x % 2 == 0),
        "zones": [
            sum(1 for x in s if 1 <= x <= 11),
            sum(1 for x in s if 12 <= x <= 22),
            sum(1 for x in s if 23 <= x <= 33),
        ],
        "max_run": max(len(r) for r in runs),
        "ac": len({abs(a - b) for a, b in combinations(s, 2)}),
    }


def score(rec: dict, ar: set[int], ab: int) -> dict:
    mode = rec.get("mode") or "ssq"
    if mode == "fushi":
        reds = {int(x) for x in (rec.get("red") or [])}
        blue = int(rec["blue"]) if rec.get("blue") is not None else None
        full6 = False
        if len(reds) >= 6:
            full6 = any(len(set(c) & ar) == 6 for c in combinations(sorted(reds), 6))
        return {
            "mode": mode,
            "red_hits": len(reds & ar),
            "blue_hit": blue == ab,
            "pool": sorted(reds),
            "blue": blue,
            "fushi_full6": full6,
            "hit_reds": sorted(reds & ar),
        }
    if mode == "dantuo":
        dan = {int(x) for x in (rec.get("dan") or [])}
        tuo = {int(x) for x in (rec.get("tuo") or [])}
        blue = int(rec["blue"]) if rec.get("blue") is not None else None
        pool = dan | tuo
        return {
            "mode": mode,
            "red_hits": len(pool & ar),
            "blue_hit": blue == ab,
            "dan": sorted(dan),
            "tuo": sorted(tuo),
            "blue": blue,
            "dan_all": bool(dan) and dan.issubset(ar),
            "dan_n": len(dan & ar),
            "hit_reds": sorted(pool & ar),
        }
    dig = [int(x) for x in (rec.get("digits") or [])]
    reds = set(dig[:6])
    blue = dig[6] if len(dig) > 6 else None
    return {
        "mode": "ssq",
        "red_hits": len(reds & ar),
        "blue_hit": blue == ab,
        "digits": dig,
        "hit_reds": sorted(reds & ar),
        "blue": blue,
    }


def retro_recs(prior: list[dict]) -> list[dict]:
    analysis = analyze_ssq(prior[:100])
    based = str(prior[0]["issue"])
    seed = period_seed(based, 0)
    exclude: set[tuple[int, ...]] = set()
    if isinstance(prior[0].get("digits"), list) and len(prior[0]["digits"]) >= 7:
        exclude.add(tuple(int(x) for x in prior[0]["digits"][:7]))
    return build_ssq_recommendations(
        analysis, seed=seed, exclude=exclude, include_dantuo=True, include_fushi=True,
    ), analysis


async def main() -> None:
    draws = await fetch_ssq_history(80, force_refresh=True)
    actual = draws[0]
    issue = str(actual["issue"])
    ar = set(actual["red"])
    ab = int(actual["blue"])
    print("=== ACTUAL ===")
    print(issue, actual.get("draw_time"), actual["result"], "morph", morph(actual["red"]))

    based = str(draws[1]["issue"])
    prior = draws[1:]
    stored = get_stored_picks("ssq", based)
    print(f"\n=== Stored picks based_on {based} -> {issue} (n={len(stored)}) ===")
    for i, p in enumerate(stored):
        sc = score(
            {
                "mode": p.get("mode") or "ssq",
                "digits": p.get("digits"),
                "red": p.get("red"),
                "dan": p.get("dan"),
                "tuo": p.get("tuo"),
                "blue": p.get("blue"),
            },
            ar,
            ab,
        )
        print(f"  stored{i+1}", p.get("display") or p.get("digits"), sc)

    recs, analysis = retro_recs(prior)
    print(f"\n=== Retro freq package (seed based {based}) ===")
    for r in recs:
        sc = score(r, ar, ab)
        print(f"  [{r.get('label')}] {r.get('display')}")
        print("   ", sc)
        if r.get("mode") == "ssq":
            print("    morph", morph(r["digits"][:6]))

    singles = [r for r in recs if r.get("mode") == "ssq"]
    blues = [int(r["digits"][6]) for r in singles]
    print("\n=== Package structure ===")
    print("singles blues:", blues, "unique:", len(set(blues)), "high(>10):", sum(1 for b in blues if b > 10))
    print("actual blue in package?", ab in blues)
    for i, a in enumerate(singles):
        for j, b in enumerate(singles):
            if i >= j:
                continue
            ov = len(set(a["digits"][:6]) & set(b["digits"][:6]))
            print(f"  overlap {i+1}-{j+1}: {ov}")
    fushi = next(r for r in recs if r.get("mode") == "fushi")
    dantuo = next(r for r in recs if r.get("mode") == "dantuo")
    print(
        "fushi cover:",
        sorted(set(fushi["red"]) & ar),
        f"{len(set(fushi['red']) & ar)}/6",
        "blue_ok",
        fushi["blue"] == ab,
    )
    print(
        "dantuo dan",
        dantuo["dan"],
        "dan_hits",
        sorted(set(dantuo["dan"]) & ar),
        "tuo_hits",
        sorted(set(dantuo["tuo"]) & ar),
        "blue_ok",
        dantuo["blue"] == ab,
    )

    print("\n=== Last 6 issues hit summary ===")
    for idx, d in enumerate(draws[:6]):
        if idx + 1 >= len(draws):
            continue
        based_i = str(draws[idx + 1]["issue"])
        picks = get_stored_picks("ssq", based_i)
        src = "stored"
        if not picks:
            src = "retro"
            rr, _ = retro_recs(draws[idx + 1 :])
            picks = [x for x in (_pick_from_rec(r) for r in rr) if x]
        elif "fushi" not in {p.get("mode") for p in picks}:
            src = "stored+retro_compound"
            rr, _ = retro_recs(draws[idx + 1 :])
            modes = {p.get("mode") or "ssq" for p in picks}
            for r in rr:
                pk = _pick_from_rec(r)
                if pk and pk.get("mode") in ("fushi", "dantuo") and pk["mode"] not in modes:
                    picks.append(pk)
                    modes.add(pk["mode"])
        ar2 = set(d["red"])
        ab2 = int(d["blue"])
        parts = []
        best = 0
        any_b = False
        for p in picks:
            sc = score(p, ar2, ab2)
            best = max(best, sc["red_hits"])
            any_b = any_b or sc["blue_hit"]
            tag = sc["mode"]
            parts.append(f"{tag}:{sc['red_hits']}{'B' if sc['blue_hit'] else ''}")
        print(
            f"  {d['issue']} {d['result']} based={based_i} [{src}] "
            f"max_red={best} any_blue={any_b} | {', '.join(parts)}"
        )

    ss = analysis.get("sum_stats") or {}
    bz = analysis.get("blue_zone") or {}
    print("\n=== Logic checklist vs tonight ===")
    print("sum_stats target_lo/hi/mean:", ss.get("target_lo"), ss.get("target_hi"), ss.get("mean"))
    print("actual sum:", sum(ar), "in_common_band?", ss.get("target_lo", 0) <= sum(ar) <= ss.get("target_hi", 200))
    print("blue_zone low_rate:", bz.get("low_rate"), "actual blue:", ab, "is_high:", ab > 10)
    print("actual morph:", morph(ar))
    print("exclude previous draw from singles?", all(
        tuple(r["digits"][:7]) != tuple(int(x) for x in prior[0]["digits"][:7]) for r in singles
    ))

    # Flag potential logic smells in current package
    flags = []
    if len(set(blues)) < len(blues):
        flags.append("single blues not unique")
    if sum(1 for b in blues if b > 10) > 1:
        flags.append(f"package has {sum(1 for b in blues if b > 10)} high blues (>1 allowed?)")
    for i, a in enumerate(singles):
        for j, b in enumerate(singles):
            if i < j and len(set(a["digits"][:6]) & set(b["digits"][:6])) >= 4:
                flags.append(f"singles {i+1}&{j+1} overlap>={4}")
    # fushi sample digits vs full red
    if len(fushi.get("red") or []) != 7:
        flags.append("fushi red count != 7")
    if len(dantuo.get("dan") or []) != 2 or len(dantuo.get("tuo") or []) != 5:
        flags.append("dantuo structure not 2+5")
    # tonight-specific: consecutive pair present — soft filter should allow
    if morph(ar)["max_run"] >= 2:
        flags.append("note: actual has consecutive run (soft preference should allow)")
    # high blue
    if ab > 10:
        flags.append("note: actual high blue; package prefers low zone — expected miss risk")
    # coverage: did any single get >=3?
    single_best = max((score(r, ar, ab)["red_hits"] for r in singles), default=0)
    if single_best <= 1:
        flags.append(f"weak coverage tonight: best single only {single_best} reds")
    fushi_hits = score(fushi, ar, ab)["red_hits"]
    if fushi_hits <= 2:
        flags.append(f"fushi only covered {fushi_hits}/6 actual reds")
    print("\n=== FLAGS ===")
    for f in flags or ["(none critical)"]:
        print(" -", f)

    # Dump next-issue package (based 2026106) for forward look
    print("\n=== Forward package based on tonight (for next draw) ===")
    fwd, _ = retro_recs(draws)
    for r in fwd:
        print(f"  [{r.get('label')}] {r.get('display')}  mode={r.get('mode')}")
        if r.get("mode") == "ssq":
            print("    morph", morph(r["digits"][:6]))


if __name__ == "__main__":
    asyncio.run(main())
