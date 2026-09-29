# -*- coding: utf-8 -*-
"""六玩法号码推荐 walk-forward 良性评估：模型 vs 随机基线。"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Callable

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from service.digital_pick import period_seed
from service.pailie_service import (
    GAME_SPECS,
    _analyze_draws,
    _build_recommendations,
    _fetch_history,
)
from service.ssq_service import analyze_ssq, build_ssq_recommendations, fetch_ssq_history
from service.dlt_service import analyze_dlt, build_dlt_recommendations, fetch_dlt_history
from service.fc3d_service import fetch_fc3d_history

N_EVAL = 40
WINDOW = 40
OUT = Path(__file__).resolve().parent / "_digital_benign_audit.json"


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _positional_hits(pred: list[int], actual: list[int]) -> int:
    n = min(len(pred), len(actual))
    return sum(1 for i in range(n) if int(pred[i]) == int(actual[i]))


def _set_hits(pred: list[int], actual: list[int]) -> int:
    return len(set(pred) & set(actual))


async def _load_game(game: str, limit: int = 100) -> list[dict]:
    if game == "ssq":
        return await fetch_ssq_history(limit, force_refresh=True)
    if game == "dlt":
        return await fetch_dlt_history(limit, force_refresh=True)
    if game == "fc3d":
        return await fetch_fc3d_history(limit, force_refresh=True)
    return await _fetch_history(game, limit, force_refresh=True)


def _recs_for(game: str, hist: list[dict], seed: int) -> list[dict]:
    if game == "ssq":
        exclude: set[tuple[int, ...]] = set()
        if hist and isinstance(hist[0].get("digits"), list) and len(hist[0]["digits"]) >= 7:
            exclude.add(tuple(int(x) for x in hist[0]["digits"][:7]))
        return build_ssq_recommendations(analyze_ssq(hist), seed=seed, exclude=exclude)
    if game == "dlt":
        exclude = set()
        if hist and isinstance(hist[0].get("digits"), list) and len(hist[0]["digits"]) >= 7:
            exclude.add(tuple(int(x) for x in hist[0]["digits"][:7]))
        return build_dlt_recommendations(analyze_dlt(hist), seed=seed, exclude=exclude)
    alphabets = GAME_SPECS[game]["alphabets"]
    analysis = _analyze_draws(hist, alphabets)
    return _build_recommendations(game, hist, analysis, seed=seed)


def _score_period(game: str, recs: list[dict], target: dict, rng: random.Random) -> dict[str, Any]:
    """返回模型与随机在同一注数下的命中指标。"""
    if game in ("pl3", "pl5", "qxc", "fc3d"):
        actual = [int(x) for x in (target.get("digits") or [])]
        alphabets = GAME_SPECS[game]["alphabets"]
        n_pos = len(alphabets)
        actual = actual[:n_pos]
        model_best = 0
        model_exact = 0
        picks = []
        for r in recs:
            if r.get("mode") not in (None, "direct", game, "ssq", "dlt") and r.get("mode") in ("dantuo", "fushi"):
                continue
            digs = [int(x) for x in (r.get("digits") or [])][:n_pos]
            if len(digs) < n_pos:
                continue
            picks.append(digs)
            h = _positional_hits(digs, actual)
            model_best = max(model_best, h)
            if h == n_pos:
                model_exact = 1
        # 取前 5 注
        picks = picks[:5]
        n_tickets = max(1, len(picks))
        rand_best = 0
        rand_exact = 0
        for _ in range(n_tickets):
            rr = [rng.randrange(alphabets[i]) for i in range(n_pos)]
            h = _positional_hits(rr, actual)
            rand_best = max(rand_best, h)
            if h == n_pos:
                rand_exact = 1
        return {
            "metric": "positional_hits",
            "n_pos": n_pos,
            "n_tickets": n_tickets,
            "model_best": model_best,
            "rand_best": rand_best,
            "model_exact": model_exact,
            "rand_exact": rand_exact,
            "model_avg_ticket_hits": _avg([_positional_hits(p, actual) for p in picks]) if picks else 0,
        }

    if game == "ssq":
        ar = set(target.get("red") or [])
        ab = int(target.get("blue") or 0)
        model_red = 0
        model_blue = 0
        singles = []
        for r in recs:
            mode = r.get("mode")
            # 公平对照：仅统计单式（复式/胆拖号池更大，会虚高命中）
            if mode in ("fushi", "dantuo"):
                continue
            reds = set(int(x) for x in (r.get("red") or (r.get("digits") or [])[:6]))
            blue = r.get("blue")
            if blue is None and r.get("digits") and len(r["digits"]) > 6:
                blue = r["digits"][6]
            if len(reds) != 6:
                continue
            singles.append(reds)
            model_red = max(model_red, len(reds & ar))
            if blue == ab:
                model_blue = 1
        n_tickets = max(3, len(singles) or 3)
        rand_red = 0
        rand_blue = 0
        for _ in range(n_tickets):
            rr = set(rng.sample(range(1, 34), 6))
            bb = rng.randint(1, 16)
            rand_red = max(rand_red, len(rr & ar))
            if bb == ab:
                rand_blue = 1
        return {
            "metric": "ssq_hits_singles_only",
            "n_tickets": n_tickets,
            "model_best": model_red,
            "rand_best": rand_red,
            "model_blue": model_blue,
            "rand_blue": rand_blue,
        }

    # dlt
    af = set(target.get("front") or (target.get("digits") or [])[:5])
    ab = set(target.get("back") or (target.get("digits") or [])[5:7])
    model_f = 0
    model_b = 0
    n = 0
    for r in recs:
        digs = [int(x) for x in (r.get("digits") or [])]
        if len(digs) < 7:
            front = [int(x) for x in (r.get("front") or [])]
            back = [int(x) for x in (r.get("back") or [])]
        else:
            front, back = digs[:5], digs[5:7]
        if len(front) < 5 or len(back) < 2:
            continue
        model_f = max(model_f, len(set(front) & af))
        model_b = max(model_b, len(set(back) & ab))
        n += 1
    n_tickets = max(5, n or 5)
    rand_f = 0
    rand_b = 0
    for _ in range(n_tickets):
        rf = set(rng.sample(range(1, 36), 5))
        rb = set(rng.sample(range(1, 13), 2))
        rand_f = max(rand_f, len(rf & af))
        rand_b = max(rand_b, len(rb & ab))
    return {
        "metric": "dlt_hits",
        "n_tickets": n_tickets,
        "model_best": model_f,
        "rand_best": rand_f,
        "model_back": model_b,
        "rand_back": rand_b,
    }


async def audit_game(game: str) -> dict[str, Any]:
    draws = await _load_game(game, 100)
    if len(draws) < WINDOW + 10:
        return {"game": game, "error": f"insufficient draws: {len(draws)}"}

    rng = random.Random(42 + sum(ord(c) for c in game) * 17)
    rows = []
    for i in range(min(N_EVAL, len(draws) - WINDOW - 1)):
        target = draws[i]
        hist = draws[i + 1 : i + 1 + WINDOW]
        if len(hist) < WINDOW:
            break
        seed = period_seed(str(hist[0].get("issue") or i), 0)
        try:
            recs = _recs_for(game, hist, seed)
        except Exception as e:
            rows.append({"issue": target.get("issue"), "error": str(e)})
            continue
        scored = _score_period(game, recs, target, rng)
        scored["issue"] = target.get("issue")
        scored["result"] = target.get("result")
        rows.append(scored)

    ok = [r for r in rows if "error" not in r]
    summary: dict[str, Any] = {
        "game": game,
        "name": GAME_SPECS.get(game, {}).get("name") or game,
        "periods": len(ok),
        "newest": draws[0].get("issue") if draws else None,
        "oldest_eval": ok[-1].get("issue") if ok else None,
    }
    if not ok:
        summary["error"] = "no scored periods"
        return summary

    summary["model_avg_best"] = round(_avg([float(r["model_best"]) for r in ok]), 3)
    summary["rand_avg_best"] = round(_avg([float(r["rand_best"]) for r in ok]), 3)
    summary["delta_best"] = round(summary["model_avg_best"] - summary["rand_avg_best"], 3)

    if game in ("pl3", "pl5", "qxc", "fc3d"):
        summary["model_exact_rate"] = round(_avg([float(r["model_exact"]) for r in ok]), 3)
        summary["rand_exact_rate"] = round(_avg([float(r["rand_exact"]) for r in ok]), 3)
        summary["delta_exact"] = round(summary["model_exact_rate"] - summary["rand_exact_rate"], 3)
        summary["n_pos"] = ok[0].get("n_pos")
    elif game == "ssq":
        summary["model_blue_rate"] = round(_avg([float(r["model_blue"]) for r in ok]), 3)
        summary["rand_blue_rate"] = round(_avg([float(r["rand_blue"]) for r in ok]), 3)
        summary["delta_blue"] = round(summary["model_blue_rate"] - summary["rand_blue_rate"], 3)
    elif game == "dlt":
        summary["model_back_avg"] = round(_avg([float(r["model_back"]) for r in ok]), 3)
        summary["rand_back_avg"] = round(_avg([float(r["rand_back"]) for r in ok]), 3)
        summary["delta_back"] = round(summary["model_back_avg"] - summary["rand_back_avg"], 3)

    # 良性判定：相对随机不显著变差（|Δ| 容忍带），且不做必中宣称
    # 位置类：每期最佳命中位数差；集合类：红/前区命中差
    tol = 0.15 if game in ("pl3", "fc3d") else 0.25
    if game in ("pl5", "qxc"):
        tol = 0.35
    if game in ("ssq", "dlt"):
        tol = 0.20
    delta = summary["delta_best"]
    if delta >= -tol:
        verdict = "benign" if delta <= tol * 1.5 else "mild_edge_noise"
    else:
        verdict = "weak_vs_random"
    summary["tolerance"] = tol
    summary["verdict"] = verdict
    summary["recent10"] = [
        {
            "issue": r.get("issue"),
            "result": r.get("result"),
            "model": r.get("model_best"),
            "rand": r.get("rand_best"),
        }
        for r in ok[:10]
    ]
    return summary


async def main() -> None:
    games = ["pl3", "pl5", "qxc", "ssq", "dlt", "fc3d"]
    results = []
    for g in games:
        print(f"=== auditing {g} ===", flush=True)
        try:
            s = await audit_game(g)
        except Exception as e:
            s = {"game": g, "error": str(e)}
        results.append(s)
        print(json.dumps(s, ensure_ascii=False, indent=2), flush=True)

    payload = {
        "meta": {
            "n_eval": N_EVAL,
            "window": WINDOW,
            "note": "walk-forward frequency/position picks vs fair random baseline; entertainment reference only",
            "community_refs": [
                "zxz0119/lottery-ai-simulator (hot/cold/miss + backtest, not guarantee)",
                "zhaoyangpp/LottoProphet (LSTM-CRF; research UI)",
                "Markovmodcn/Lotterymcp (cold/hot/sum/span/zone analysis tools)",
                "sinyu1012/Double-Color-Ball-AI (hot/cold/balance/cycle strategies)",
            ],
        },
        "games": results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
