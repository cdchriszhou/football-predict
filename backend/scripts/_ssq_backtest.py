# -*- coding: utf-8 -*-
"""SSQ recommendation walk-forward backtest (frequency picks vs random baseline)."""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from service.digital_pick import period_seed
from service.ssq_service import analyze_ssq, build_ssq_recommendations, fetch_ssq_history

N_EVAL = 50
WINDOW = 40
CACHE_PATH = Path(__file__).resolve().parent / "_ssq_history_cache.json"
OUT_PATH = Path(__file__).resolve().parent / "_ssq_backtest_out.json"


def _ensure_newest_first(draws: list[dict]) -> list[dict]:
    if len(draws) < 2:
        return draws
    a, b = str(draws[0].get("issue") or ""), str(draws[-1].get("issue") or "")
    if a and b and a < b:
        return list(reversed(draws))
    return draws


def _load_cache() -> list[dict]:
    if not CACHE_PATH.exists():
        return []
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_cache(draws: list[dict]) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(draws, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[warn] failed to save cache: {e}", file=sys.stderr)


async def _load_draws(limit: int = 100) -> tuple[list[dict], str]:
    draws: list[dict] = []
    source = "network"
    try:
        draws = await fetch_ssq_history(limit, force_refresh=True)
    except Exception as e:
        print(f"[warn] fetch_ssq_history error: {e}", file=sys.stderr)
        draws = []

    if len(draws) < WINDOW + 10:
        cached = _load_cache()
        if len(cached) > len(draws):
            draws = cached
            source = "local_cache"
            print(f"[info] using local cache ({len(draws)} draws)", file=sys.stderr)
    else:
        _save_cache(draws)

    draws = _ensure_newest_first(draws)
    return draws, source


def _red_set(rec: dict) -> set[int]:
    mode = rec.get("mode")
    if mode == "fushi":
        reds = rec.get("red") or []
        return {int(x) for x in reds}
    if mode == "dantuo":
        dan = rec.get("dan") or []
        tuo = rec.get("tuo") or []
        if dan or tuo:
            return {int(x) for x in list(dan) + list(tuo)}
    reds = rec.get("red")
    if isinstance(reds, list) and reds:
        return {int(x) for x in reds[:6]}
    digits = rec.get("digits") or []
    return {int(x) for x in digits[:6]}


def _blue_of(rec: dict) -> int | None:
    b = rec.get("blue")
    if isinstance(b, int):
        return b
    digits = rec.get("digits") or []
    if len(digits) >= 7:
        try:
            return int(digits[6])
        except (TypeError, ValueError):
            return None
    return None


def _score_rec(rec: dict, actual_red: set[int], actual_blue: int) -> dict[str, Any]:
    mode = rec.get("mode") or "ssq"
    red_pool = _red_set(rec)
    blue = _blue_of(rec)
    red_hits = len(red_pool & actual_red)
    blue_hit = bool(blue is not None and int(blue) == int(actual_blue))

    fushi_full6 = False
    dan_hit = None
    if mode == "fushi" and len(red_pool) >= 6:
        fushi_full6 = any(len(set(c) & actual_red) == 6 for c in combinations(sorted(red_pool), 6))
        # also sample single from digits for alternate view
        sample = rec.get("digits") or []
        sample_red = {int(x) for x in sample[:6]} if len(sample) >= 6 else set()
        sample_hits = len(sample_red & actual_red) if sample_red else red_hits
    else:
        sample_hits = red_hits

    if mode == "dantuo":
        dan = {int(x) for x in (rec.get("dan") or [])}
        dan_hit = bool(dan) and dan.issubset(actual_red)
        # coverage hits already in red_hits; sample digits hits separately
        sample = rec.get("digits") or []
        sample_red = {int(x) for x in sample[:6]} if len(sample) >= 6 else set()
        sample_hits = len(sample_red & actual_red) if sample_red else red_hits

    return {
        "mode": mode,
        "red_hits": red_hits,
        "sample_red_hits": sample_hits,
        "blue_hit": blue_hit,
        "blue": blue,
        "fushi_full6": fushi_full6,
        "dan_hit": dan_hit,
    }


def _random_singles(rng: random.Random, n: int = 5) -> list[dict]:
    out = []
    for i in range(n):
        reds = sorted(rng.sample(range(1, 34), 6))
        blue = rng.randint(1, 16)
        out.append({
            "id": f"rand-{i + 1}",
            "mode": "ssq",
            "red": reds,
            "blue": blue,
            "digits": reds + [blue],
        })
    return out


def _agg_period_scores(scores: list[dict]) -> dict[str, Any]:
    best_red = max((s["red_hits"] for s in scores), default=0)
    any_blue = any(s["blue_hit"] for s in scores)
    primary_blue = bool(scores and scores[0]["blue_hit"])
    any_r3b = any(s["red_hits"] >= 3 and s["blue_hit"] for s in scores)
    any_r4 = any(s["red_hits"] >= 4 for s in scores)
    any_r5 = any(s["red_hits"] >= 5 for s in scores)
    any_r6 = any(s["red_hits"] >= 6 for s in scores)
    # for fushi, also count C(7,6) full red as red==6
    any_r6 = any_r6 or any(s.get("fushi_full6") for s in scores)
    blue_alone = any_blue and not any_r3b
    return {
        "best_red_hits": best_red,
        "any_blue": any_blue,
        "primary_blue": primary_blue,
        "prize_like": {
            "red3_and_blue": any_r3b,
            "red_ge_4": any_r4,
            "red_ge_5": any_r5,
            "red_eq_6": any_r6,
            "blue_alone": blue_alone,
        },
    }


def _finalize(periods: list[dict], label: str, all_pick_blues: list[int],
              blue_hit_low: list[bool], blue_hit_high: list[bool]) -> dict[str, Any]:
    n = len(periods) or 1
    max_dist = Counter(p["best_red_hits"] for p in periods)
    prize = Counter()
    for p in periods:
        for k, v in p["prize_like"].items():
            if v:
                prize[k] += 1

    total_picks = len(all_pick_blues) or 1
    blue_gt10 = sum(1 for b in all_pick_blues if b is not None and b > 10)

    return {
        "label": label,
        "periods": len(periods),
        "avg_best_red_hits": round(sum(p["best_red_hits"] for p in periods) / n, 4),
        "avg_any_blue_hit_rate": round(sum(1 for p in periods if p["any_blue"]) / n, 4),
        "avg_primary_blue_hit_rate": round(sum(1 for p in periods if p["primary_blue"]) / n, 4),
        "max_red_hits_distribution": {str(k): max_dist.get(k, 0) for k in range(0, 7)},
        "prize_like_counts": {
            "red3_and_blue": prize.get("red3_and_blue", 0),
            "red_ge_4": prize.get("red_ge_4", 0),
            "red_ge_5": prize.get("red_ge_5", 0),
            "red_eq_6": prize.get("red_eq_6", 0),
            "blue_alone": prize.get("blue_alone", 0),
        },
        "prize_like_rates": {
            "red3_and_blue": round(prize.get("red3_and_blue", 0) / n, 4),
            "red_ge_4": round(prize.get("red_ge_4", 0) / n, 4),
            "red_ge_5": round(prize.get("red_ge_5", 0) / n, 4),
            "red_eq_6": round(prize.get("red_eq_6", 0) / n, 4),
            "blue_alone": round(prize.get("blue_alone", 0) / n, 4),
        },
        "blue_gt10_pick_share": round(blue_gt10 / total_picks, 4),
        "blue_gt10_pick_count": blue_gt10,
        "total_picks_scored": total_picks,
        "blue_hit_when_actual_le_10": {
            "n": len(blue_hit_low),
            "hits": sum(1 for x in blue_hit_low if x),
            "rate": round(sum(1 for x in blue_hit_low if x) / max(1, len(blue_hit_low)), 4),
        },
        "blue_hit_when_actual_gt_10": {
            "n": len(blue_hit_high),
            "hits": sum(1 for x in blue_hit_high if x),
            "rate": round(sum(1 for x in blue_hit_high if x) / max(1, len(blue_hit_high)), 4),
        },
    }


async def main() -> dict[str, Any]:
    draws, source = await _load_draws(100)
    if len(draws) < WINDOW + 1:
        summary = {
            "error": "insufficient_draws",
            "draw_count": len(draws),
            "source": source,
            "need_at_least": WINDOW + 1,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        OUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    max_eval = min(N_EVAL, len(draws) - WINDOW)
    model_periods: list[dict] = []
    rand_periods: list[dict] = []
    model_blues: list[int] = []
    rand_blues: list[int] = []
    model_blue_low: list[bool] = []
    model_blue_high: list[bool] = []
    rand_blue_low: list[bool] = []
    rand_blue_high: list[bool] = []

    dantuo_dan_hits = 0
    dantuo_n = 0
    fushi_full6_n = 0
    fushi_n = 0
    period_details: list[dict] = []

    rng = random.Random(20260907)

    for i in range(max_eval):
        target = draws[i]
        history = draws[i + 1 : i + 1 + WINDOW]
        if len(history) < WINDOW:
            break

        actual_red = set(int(x) for x in (target.get("red") or []))
        actual_blue = int(target["blue"])
        if len(actual_red) != 6:
            continue

        analysis = analyze_ssq(history)
        seed = period_seed(str(history[0]["issue"]), 0) if history else 0
        exclude: set[tuple[int, ...]] = set()
        if history and history[0].get("digits"):
            exclude.add(tuple(int(x) for x in history[0]["digits"][:7]))

        recs = build_ssq_recommendations(analysis, seed=seed, exclude=exclude)
        scores = [_score_rec(r, actual_red, actual_blue) for r in recs]
        agg = _agg_period_scores(scores)
        model_periods.append(agg)

        for s in scores:
            if s["blue"] is not None:
                model_blues.append(int(s["blue"]))
            if s["mode"] == "dantuo":
                dantuo_n += 1
                if s.get("dan_hit"):
                    dantuo_dan_hits += 1
            if s["mode"] == "fushi":
                fushi_n += 1
                if s.get("fushi_full6"):
                    fushi_full6_n += 1

        if actual_blue <= 10:
            model_blue_low.append(agg["any_blue"])
        else:
            model_blue_high.append(agg["any_blue"])

        # random baseline
        rrecs = _random_singles(rng, 5)
        rscores = [_score_rec(r, actual_red, actual_blue) for r in rrecs]
        ragg = _agg_period_scores(rscores)
        rand_periods.append(ragg)
        for s in rscores:
            if s["blue"] is not None:
                rand_blues.append(int(s["blue"]))
        if actual_blue <= 10:
            rand_blue_low.append(ragg["any_blue"])
        else:
            rand_blue_high.append(ragg["any_blue"])

        period_details.append({
            "issue": target.get("issue"),
            "based_on_issue": history[0].get("issue") if history else None,
            "actual": target.get("result"),
            "actual_blue": actual_blue,
            "model_best_red": agg["best_red_hits"],
            "model_any_blue": agg["any_blue"],
            "random_best_red": ragg["best_red_hits"],
            "random_any_blue": ragg["any_blue"],
            "pick_scores": scores,
        })

    model_summary = _finalize(model_periods, "model", model_blues, model_blue_low, model_blue_high)
    rand_summary = _finalize(rand_periods, "random", rand_blues, rand_blue_low, rand_blue_high)

    summary: dict[str, Any] = {
        "meta": {
            "draw_count": len(draws),
            "source": source,
            "newest_issue": draws[0].get("issue") if draws else None,
            "oldest_issue": draws[-1].get("issue") if draws else None,
            "n_eval_requested": N_EVAL,
            "window": WINDOW,
            "periods_evaluated": len(model_periods),
            "ordering": "newest_first",
        },
        "model": model_summary,
        "random_baseline": rand_summary,
        "extras": {
            "dantuo_dan_hit_rate": round(dantuo_dan_hits / max(1, dantuo_n), 4),
            "dantuo_n": dantuo_n,
            "fushi_full6_rate": round(fushi_full6_n / max(1, fushi_n), 4),
            "fushi_n": fushi_n,
        },
        "delta_model_minus_random": {
            "avg_best_red_hits": round(
                model_summary["avg_best_red_hits"] - rand_summary["avg_best_red_hits"], 4
            ),
            "avg_any_blue_hit_rate": round(
                model_summary["avg_any_blue_hit_rate"] - rand_summary["avg_any_blue_hit_rate"], 4
            ),
            "avg_primary_blue_hit_rate": round(
                model_summary["avg_primary_blue_hit_rate"] - rand_summary["avg_primary_blue_hit_rate"], 4
            ),
        },
        "periods": period_details,
    }

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"\n[saved] {OUT_PATH}", file=sys.stderr)
    return summary


if __name__ == "__main__":
    asyncio.run(main())
