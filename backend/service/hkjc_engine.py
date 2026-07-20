"""Four-layer HKJC recommendation engine (rules + scoring + ML proxy + odds adjustment)."""
from __future__ import annotations

import math
from copy import deepcopy


WEIGHTS = {
    "distance_track": 0.28,
    "recent_form": 0.22,
    "jockey_pair": 0.16,
    "trainer": 0.12,
    "draw": 0.10,
    "rating": 0.12,
}

DISTANCE_PENALTY = {
    "短途": {"长途": -0.18, "中距": -0.08},
    "中距": {"长途": -0.10, "短途": -0.05},
    "长途": {"短途": -0.20, "中距": -0.06},
}


def _rule_adjustments(runner: dict, race: dict) -> tuple[float, list[str]]:
    """Layer 1: professional rule engine."""
    delta = 0.0
    notes: list[str] = []
    dist_cat = race.get("distance_category", "中距")
    tags = runner.get("tags") or []

    # Distance / surface fit from stats (already in score); penalize mismatch via tags
    if "长途" in tags and dist_cat == "短途":
        delta -= 0.12
        notes.append("长途马跑短途，规则降权")
    if "泥地" in tags and race.get("track_type") == "草地":
        delta -= 0.15
        notes.append("泥地偏好马跑草地，规则降权")

    # Draw extremes on tight tracks
    draw = runner.get("draw", 0)
    if draw >= 10:
        delta -= 0.05
        notes.append("外档不利，档位减分")
    elif draw == 1:
        delta += 0.03
        notes.append("内档占优，档位加分")

    # Form slump
    form = runner.get("recent_form", "")
    if form.startswith("7") or form.startswith("8") or form.startswith("9"):
        delta -= 0.10
        notes.append("近期状态低迷，规则降权")

    # Weight anomaly
    wd = runner.get("weight_delta") or 0
    if abs(wd) >= 3:
        delta -= 0.08
        notes.append(f"体重异动({wd:+.1f}lb)，标记高风险")

    # Head-to-head boost placeholder via high win rate
    stats = runner.get("stats") or {}
    if stats.get("win_rate_10", 0) >= 0.25:
        notes.append("近10场胜率突出，对战规则加分")
        delta += 0.04

    return delta, notes


def _base_score(runner: dict) -> tuple[float, dict]:
    """Layer 2: weighted multi-factor score."""
    stats = runner.get("stats") or {}
    components = {
        "distance_track": (stats.get("distance_fit", 0.5) + stats.get("track_fit", 0.5)) / 2,
        "recent_form": stats.get("win_rate_10", 0) * 0.6 + stats.get("place_rate_10", 0) * 0.4,
        "jockey_pair": stats.get("jockey_pair_rate", 0.15),
        "trainer": stats.get("trainer_rate", 0.15),
        "draw": stats.get("draw_fit", 0.75),
        "rating": min(runner.get("rating", 60) / 100.0, 1.0),
    }
    score = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    return score, {k: round(v, 3) for k, v in components.items()}


def _ml_probabilities(scores: list[float]) -> list[float]:
    """Layer 3: softmax proxy for win probability."""
    if not scores:
        return []
    mx = max(scores)
    exps = [math.exp(s - mx) for s in scores]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


def _odds_adjustment(runner: dict, model_rank: int, market_rank: int) -> tuple[float, str | None]:
    """Layer 4: market odds vs model divergence."""
    odds = runner.get("odds") or 10.0
    implied = 1.0 / odds if odds > 0 else 0.05
    rank_gap = market_rank - model_rank
    note = None
    adj = 0.0
    if rank_gap >= 3 and implied > 0.12:
        adj += 0.04
        note = "市场低估，赔率偏高，潜力选项"
    elif rank_gap <= -3 and implied < 0.20:
        adj -= 0.05
        note = "异常热门，资金扎堆，上调风险"
    elif model_rank <= 2 and implied < 0.35:
        note = "合理热门，实力与赔率匹配"
    return adj, note


def _tier(win_p: float, risk_flags: list[str], rank: int) -> str:
    if any("异动" in f or "低迷" in f for f in risk_flags):
        return "exclude"
    if win_p >= 0.22 and rank <= 2 and not risk_flags:
        return "primary"
    if win_p >= 0.14 and rank <= 4:
        return "secondary"
    if rank <= 5 and win_p >= 0.08:
        return "dark_horse"
    return "exclude"


def is_race_finished(race: dict) -> bool:
    if race.get("is_finished"):
        return True
    runners = race.get("runners") or []
    return any(r.get("actual_placing") for r in runners)


def _winner_and_placings(race: dict) -> tuple[dict | None, list[dict]]:
    runners = race.get("runners") or []
    ordered = sorted(runners, key=lambda r: int(r.get("actual_placing") or 99))
    winner = next((r for r in ordered if int(r.get("actual_placing") or 0) == 1), None)
    top3 = [r for r in ordered if int(r.get("actual_placing") or 99) <= 3]
    return winner, top3


def _race_result_summary(race: dict) -> str:
    winner, top3 = _winner_and_placings(race)
    if not winner:
        return f"第{race['race_no']}场已完赛，赛果待确认。"
    top3_names = "、".join(
        f"{r.get('name')}({int(r.get('actual_placing') or 0)}名)"
        for r in top3[:3]
    )
    odds = winner.get("odds")
    odds_text = f"，独赢 {odds}" if odds else ""
    return (
        f"第{race['race_no']}场（{race['distance_m']}米{race.get('class') or ''}）已完赛。"
        f"冠军 {winner.get('name')}（{winner.get('horse_no')}号，{winner.get('jockey') or '—'}）"
        f"{odds_text}。"
        f"头三名：{top3_names or '—'}。"
    )


def analyze_race_result(race: dict) -> dict:
    """Post-race view: official finishing order, no pre-race picks."""
    winner, top3 = _winner_and_placings(race)
    runners = sorted(
        race.get("runners") or [],
        key=lambda r: int(r.get("actual_placing") or 99),
    )
    rankings = []
    for r in runners:
        placing = int(r.get("actual_placing") or 0)
        rankings.append({
            **r,
            "placing": placing,
            "model_rank": placing,
            "market_rank": placing,
            "win_probability": 0.0,
            "place_probability": 0.0,
            "tier": "result",
            "risk_flags": [],
            "odds_note": None,
            "feature_breakdown": [],
            "analysis_snippet": (
                f"第{placing}名 · 骑师 {r.get('jockey') or '—'}"
                f" · 练马师 {r.get('trainer') or '—'}"
            ),
        })
    return {
        "mode": "result",
        "rankings": rankings,
        "picks": {"primary": [], "secondary": [], "dark_horse": []},
        "race_summary": _race_result_summary(race),
        "avoid": False,
        "meeting_risk": race.get("risk_level"),
        "result": {
            "winner_horse_no": winner.get("horse_no") if winner else None,
            "winner_name": winner.get("name") if winner else None,
            "top3": top3,
        },
    }


def analyze_race(race: dict, *, use_ai: bool = False) -> dict:
    """Full analysis for one race (preview) or official result recap.

    When use_ai=True and an LLM API is configured, rankings fuse quantitative
    scores (55%) with AI assessment (45%). Batch endpoints should keep use_ai=False.
    """
    if is_race_finished(race):
        return analyze_race_result(race)
    runners = deepcopy(race.get("runners") or [])
    if not runners:
        return {"rankings": [], "picks": {}, "race_summary": "", "avoid": False}

    scored = []
    for r in runners:
        base, components = _base_score(r)
        rule_delta, rule_notes = _rule_adjustments(r, race)
        total = base + rule_delta
        scored.append({
            "runner": r,
            "base_score": round(base, 4),
            "rule_delta": round(rule_delta, 4),
            "total_score": round(total, 4),
            "components": components,
            "rule_notes": rule_notes,
        })

    scored.sort(key=lambda x: -x["total_score"])
    raw_scores = [s["total_score"] for s in scored]
    win_probs = _ml_probabilities(raw_scores)

    market_sorted = sorted(runners, key=lambda x: x.get("odds", 99))
    market_rank_map = {m["horse_no"]: i + 1 for i, m in enumerate(market_sorted)}

    rankings = []
    for i, item in enumerate(scored):
        r = item["runner"]
        win_p = win_probs[i]
        place_p = min(win_p * 2.4, 0.85)
        model_rank = i + 1
        mkt_rank = market_rank_map.get(r["horse_no"], model_rank)
        odds_adj, odds_note = _odds_adjustment(r, model_rank, mkt_rank)
        win_p_adj = max(0.01, min(0.65, win_p + odds_adj))
        risk_flags = list(item["rule_notes"])
        if odds_note and "风险" in (odds_note or ""):
            risk_flags.append(odds_note)
        tier = _tier(win_p_adj, risk_flags, model_rank)

        feature_breakdown = []
        for k, v in item["components"].items():
            contrib = round(v * WEIGHTS.get(k, 0), 3)
            feature_breakdown.append({
                "key": k,
                "value": v,
                "weight": WEIGHTS.get(k, 0),
                "contribution": contrib,
            })
        if item["rule_delta"]:
            feature_breakdown.append({
                "key": "rules",
                "value": item["rule_delta"],
                "weight": 1,
                "contribution": item["rule_delta"],
            })

        rankings.append({
            **r,
            "model_rank": model_rank,
            "market_rank": mkt_rank,
            "win_probability": round(win_p_adj, 4),
            "place_probability": round(place_p, 4),
            "tier": tier,
            "risk_flags": risk_flags,
            "odds_note": odds_note,
            "feature_breakdown": feature_breakdown,
            "analysis_snippet": _analysis_snippet(r, race, win_p_adj, item["rule_notes"]),
        })

    primary = [x for x in rankings if x["tier"] == "primary"]
    secondary = [x for x in rankings if x["tier"] == "secondary"]
    dark = [x for x in rankings if x["tier"] == "dark_horse"]

    avoid = race.get("risk_level") == "high" and len(primary) == 0

    quant_result = {
        "mode": "preview",
        "rankings": rankings,
        "picks": {
            "primary": primary,
            "secondary": secondary,
            "dark_horse": dark,
        },
        "race_summary": _race_summary(race, primary, avoid),
        "avoid": avoid,
        "meeting_risk": race.get("risk_level"),
        "race_no": race.get("race_no"),
        "distance_m": race.get("distance_m"),
        "class": race.get("class"),
        "track_type": race.get("track_type"),
    }

    quant_result["ai_enabled"] = False
    return quant_result


async def analyze_race_async(race: dict, *, use_ai: bool = True) -> dict:
    """Async wrapper: quantitative analysis plus optional LLM fusion."""
    quant_result = analyze_race(race, use_ai=False)
    if not use_ai or is_race_finished(race) or quant_result.get("mode") == "result":
        return quant_result
    if not quant_result.get("rankings"):
        return quant_result

    from service.hkjc_ai import fuse_ai_with_quant_analysis, is_hkjc_ai_available, predict_race_ranking

    if not is_hkjc_ai_available():
        quant_result["ai_unavailable_reason"] = "未配置 AI API Key 或未启用大模型"
        return quant_result

    ai_payload = await predict_race_ranking(race, quant_result["rankings"])
    if not ai_payload:
        quant_result["ai_unavailable_reason"] = "AI 分析暂不可用，已使用量化排名"
        return quant_result
    return fuse_ai_with_quant_analysis(quant_result, ai_payload)


def _analysis_snippet(runner: dict, race: dict, win_p: float, notes: list[str]) -> str:
    parts = [
        f"{runner['name']}（{runner['jockey']}/{runner['trainer']}）",
        f"{race['distance_m']}米{race.get('track_type', '')}",
        f"模型胜率{win_p * 100:.1f}%",
    ]
    stats = runner.get("stats") or {}
    if stats.get("distance_fit", 0) >= 0.85:
        parts.append("同程同地适配度高")
    if stats.get("jockey_pair_rate", 0) >= 0.20:
        parts.append("骑师马匹搭档稳定")
    if notes:
        parts.append("；".join(notes[:2]))
    return "。".join(parts) + "。"


def _race_summary(race: dict, primary: list, avoid: bool) -> str:
    if avoid:
        return (
            f"第{race['race_no']}场（{race['distance_m']}米{race['class']}）波动较大，"
            "历史乱局频发，建议谨慎参考。"
        )
    if primary:
        names = "、".join(p["name"] for p in primary[:2])
        return (
            f"第{race['race_no']}场{race['distance_m']}米{race['class']}，"
            f"模型首选 {names}，同场实力分层清晰。"
        )
    return f"第{race['race_no']}场赛事开放，建议以次选及冷门参考为主。"


def analyze_meeting_result_row(race: dict) -> dict:
    winner, _ = _winner_and_placings(race)
    return {
        "race_id": race["id"],
        "race_no": race["race_no"],
        "distance_m": race["distance_m"],
        "class": race["class"],
        "winner_horse_no": winner.get("horse_no") if winner else None,
        "winner_name": winner.get("name") if winner else None,
        "winner_jockey": winner.get("jockey") if winner else None,
        "winner_odds": winner.get("odds") if winner else None,
        "summary": _race_result_summary(race),
    }


TIER_ADVICE_ZH = {
    "primary": "稳健首选",
    "secondary": "次选参考",
    "dark_horse": "冷门潜力",
    "exclude": "不建议参考",
}


def _runner_purchase_row(runner: dict) -> dict | None:
    tier = runner.get("tier", "exclude")
    if tier == "exclude":
        return None
    return {
        "horse_no": runner.get("horse_no"),
        "name": runner.get("name"),
        "jockey": runner.get("jockey"),
        "trainer": runner.get("trainer"),
        "draw": runner.get("draw"),
        "win_probability": runner.get("win_probability"),
        "place_probability": runner.get("place_probability"),
        "odds": runner.get("odds"),
        "tier": tier,
        "advice": TIER_ADVICE_ZH.get(tier, tier),
        "analysis_snippet": runner.get("analysis_snippet"),
        "odds_note": runner.get("odds_note"),
    }


def analyze_race_purchase_advice(race: dict) -> dict:
    """Per-race purchase rows for the betting-advice page."""
    if is_race_finished(race):
        winner, _ = _winner_and_placings(race)
        return {
            "race_id": race["id"],
            "race_no": race["race_no"],
            "name": race.get("name"),
            "distance_m": race["distance_m"],
            "class": race.get("class"),
            "start_time": race.get("start_time"),
            "display_mode": "result",
            "avoid": False,
            "race_summary": _race_result_summary(race),
            "recommendations": [],
            "result": {
                "winner_horse_no": winner.get("horse_no") if winner else None,
                "winner_name": winner.get("name") if winner else None,
                "winner_odds": winner.get("odds") if winner else None,
            },
        }
    analysis = analyze_race(race)
    recs = []
    for row in analysis.get("rankings") or []:
        item = _runner_purchase_row(row)
        if item:
            recs.append(item)
    recs.sort(
        key=lambda x: (
            {"primary": 0, "secondary": 1, "dark_horse": 2}.get(x["tier"], 9),
            -(x.get("win_probability") or 0),
        ),
    )
    return {
        "race_id": race["id"],
        "race_no": race["race_no"],
        "name": race.get("name"),
        "distance_m": race["distance_m"],
        "class": race["class"],
        "start_time": race.get("start_time"),
        "display_mode": "preview",
        "avoid": analysis.get("avoid", False),
        "race_summary": analysis.get("race_summary", ""),
        "recommendations": recs,
        "result": None,
    }


def build_purchase_advice(meetings: list[dict], races_by_meeting: dict[str, list[dict]]) -> list[dict]:
    """Day-level purchase advice for all meetings (newest first)."""
    output = []
    for meeting in meetings:
        mid = meeting["id"]
        races = races_by_meeting.get(mid) or []
        race_rows = [analyze_race_purchase_advice(r) for r in races]
        race_rows.sort(key=lambda x: x["race_no"])
        all_finished = bool(races) and all(is_race_finished(r) for r in races)
        display_mode = "results" if meeting.get("status") == "RESULTS" or all_finished else "preview"
        preview_count = sum(1 for r in race_rows if r["display_mode"] == "preview")
        output.append({
            "meeting_id": mid,
            "date": meeting.get("date"),
            "venue": meeting.get("venue"),
            "status": meeting.get("status"),
            "track_type": meeting.get("track_type"),
            "race_count": meeting.get("race_count") or len(races),
            "display_mode": display_mode,
            "preview_race_count": preview_count,
            "races": race_rows,
        })
    return output


def analyze_meeting_picks(meeting_id: str, races: list[dict]) -> list[dict]:
    """Day-level race screening by certainty (pre-race only)."""
    results = []
    for race in races:
        if race.get("meeting_id") != meeting_id:
            continue
        if is_race_finished(race):
            row = analyze_meeting_result_row(race)
            row["display_mode"] = "result"
            results.append(row)
            continue
        analysis = analyze_race(race)
        certainty = "high"
        if race.get("risk_level") == "high" or analysis["avoid"]:
            certainty = "low"
        elif race.get("risk_level") == "medium" or not analysis["picks"]["primary"]:
            certainty = "medium"
        results.append({
            "race_id": race["id"],
            "race_no": race["race_no"],
            "distance_m": race["distance_m"],
            "class": race["class"],
            "display_mode": "preview",
            "certainty": certainty,
            "avoid": analysis["avoid"],
            "top_pick": (analysis["picks"]["primary"] or analysis["picks"]["secondary"] or [{}])[0].get("name"),
            "summary": analysis["race_summary"],
        })
    results.sort(key=lambda x: x["race_no"])
    return results
