"""HKJC race ranking via LLM, fused with the quantitative engine."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from llm.deepseek_client import _call_api, create_llm_client
from service.runtime_config import get_runtime_config, get_secret
from utils.logger import logger

QUANT_BLEND_WEIGHT = 0.55
AI_BLEND_WEIGHT = 0.45


def is_hkjc_ai_available() -> bool:
    cfg = get_runtime_config()
    slug = (cfg.get("active_model") or "").strip()
    if slug in ("", "rule_engine"):
        return False
    key = get_secret(f"{slug}_api_key")
    if key:
        return True
    if slug == "deepseek":
        from config import DEEPSEEK_API_KEY
        return bool(DEEPSEEK_API_KEY)
    return False


def _active_model_slug() -> str:
    cfg = get_runtime_config()
    slug = cfg.get("active_model") or "deepseek"
    return slug if slug != "rule_engine" else "deepseek"


def _runner_lines(race: dict, quant_rankings: list[dict]) -> str:
    quant_by_no = {r["horse_no"]: r for r in quant_rankings}
    lines = []
    for r in race.get("runners") or []:
        no = r.get("horse_no")
        q = quant_by_no.get(no) or {}
        stats = r.get("stats") or {}
        lines.append(
            f"  {no}号 {r.get('name')} | 骑师{r.get('jockey')} | 练马师{r.get('trainer')} | "
            f"档位{r.get('draw')} | 评分{r.get('rating')} | 赔率{r.get('odds')} | "
            f"近绩{r.get('recent_form') or '—'} | "
            f"量化排名{q.get('model_rank', '—')} | 量化胜率{(q.get('win_probability') or 0) * 100:.1f}% | "
            f"市场排名{q.get('market_rank', '—')}"
        )
    return "\n".join(lines) if lines else "  （无排位数据）"


def build_hkjc_race_prompt(race: dict, quant_rankings: list[dict]) -> str:
    runners_text = _runner_lines(race, quant_rankings)
    return f"""你是香港赛马专业分析师。请结合排位表、赔率与量化模型结果，对本场赛事马匹做胜率评估与排序。

【场次】第{race.get('race_no')}场 · {race.get('distance_m')}米 · {race.get('class')} · {race.get('track_type', '')}
场地状态：{race.get('going') or race.get('track_rating') or '—'}
赛事风险：{race.get('risk_level', 'medium')}

【出马表与量化参考】
{runners_text}

分析要求：
1. 综合骑师/练马师、档位、评分、赔率、近绩、同程能力；可参考量化排名但允许合理修正（尤其冷门高赔率马）
2. 所有马匹 win_probability 之和不必等于100，单场每马为0-30的百分比数字
3. tier 取值：primary（稳健首选）/ secondary（次选）/ dark_horse（冷门潜力）/ exclude（不建议）
4. 最多选2匹 primary；赔率明显偏低且实力存疑的可标 exclude 或 secondary
5. race_summary 用中文80字内概括本场格局与投注参考倾向（非投注建议）
6. confidence 为整场把握度 0.5-0.9

严格输出 JSON，不要多余文字：
{{"race_summary":"...","confidence":0.75,"avoid":false,"rankings":[{{"horse_no":1,"win_probability":12.5,"tier":"secondary","reason":"一句中文理由"}}]}}
"""


def _parse_ai_json(content: str) -> dict | None:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _norm_win_probability(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(0.65, v))


async def predict_race_ranking(race: dict, quant_rankings: list[dict]) -> dict | None:
    """Call configured LLM for per-race horse ranking."""
    if not is_hkjc_ai_available():
        return None

    slug = _active_model_slug()
    client = create_llm_client(slug)
    prompt = build_hkjc_race_prompt(race, quant_rankings)

    try:
        api_key = get_secret(f"{slug}_api_key") or getattr(client, "api_key", "")
        base_url = get_secret(f"{slug}_api_url") or getattr(client, "base_url", "")
        if not api_key:
            logger.warning("HKJC AI: no API key for %s", slug)
            return None
        data = await _call_api(
            api_key,
            base_url,
            client.model_name(),
            prompt,
            temperature=0.15,
            max_tokens=1200,
        )
        if not data:
            return None
        content = data["choices"][0]["message"]["content"]
        parsed = _parse_ai_json(content)
        if not parsed or not isinstance(parsed.get("rankings"), list):
            logger.warning("HKJC AI: invalid rankings JSON from %s", slug)
            return None
        parsed["model_used"] = client.model_name()
        parsed["provider"] = slug
        return parsed
    except (httpx.TimeoutException, httpx.HTTPError, KeyError, IndexError) as e:
        logger.warning("HKJC AI predict failed (%s): %s", slug, e)
        return None


def fuse_ai_with_quant_analysis(quant: dict, ai: dict | None) -> dict:
    """Blend AI rankings into quantitative analyze_race output."""
    if not ai or not quant.get("rankings"):
        return {
            **quant,
            "ai_enabled": False,
            "ai_model": None,
            "ai_provider": None,
        }

    from service.hkjc_engine import _analysis_snippet, _tier

    ai_map: dict[int, dict] = {}
    for row in ai.get("rankings") or []:
        try:
            no = int(row.get("horse_no"))
        except (TypeError, ValueError):
            continue
        ai_map[no] = row

    fused: list[dict] = []
    for row in quant["rankings"]:
        no = row["horse_no"]
        ai_row = ai_map.get(no) or {}
        q_prob = float(row.get("win_probability") or 0)
        ai_prob = _norm_win_probability(ai_row.get("win_probability"))
        blend = max(0.01, min(0.65, QUANT_BLEND_WEIGHT * q_prob + AI_BLEND_WEIGHT * ai_prob))
        ai_reason = (ai_row.get("reason") or "").strip()
        ai_tier = (ai_row.get("tier") or "").strip().lower()
        new_row = {
            **row,
            "quant_win_probability": round(q_prob, 4),
            "ai_win_probability": round(ai_prob, 4),
            "win_probability": round(blend, 4),
            "place_probability": round(min(blend * 2.4, 0.85), 4),
            "ai_reason": ai_reason,
            "ai_tier": ai_tier if ai_tier in ("primary", "secondary", "dark_horse", "exclude") else None,
        }
        fused.append(new_row)

    fused.sort(key=lambda x: -x["win_probability"])
    for i, row in enumerate(fused):
        row["model_rank"] = i + 1
        row["tier"] = _tier(
            row["win_probability"],
            row.get("risk_flags") or [],
            i + 1,
        )
        notes = list(row.get("risk_flags") or [])
        if row.get("ai_reason"):
            notes.append(row["ai_reason"][:40])
        row["analysis_snippet"] = _analysis_snippet(
            row, {"distance_m": quant.get("distance_m") or row.get("distance_m"), "track_type": row.get("track_type", "")},
            row["win_probability"],
            notes,
        )

    primary = [x for x in fused if x["tier"] == "primary"]
    secondary = [x for x in fused if x["tier"] == "secondary"]
    dark = [x for x in fused if x["tier"] == "dark_horse"]
    avoid = bool(ai.get("avoid")) or quant.get("avoid", False)

    race_stub = {
        "race_no": quant.get("race_no"),
        "distance_m": quant.get("distance_m"),
        "class": quant.get("class"),
    }
    summary = (ai.get("race_summary") or "").strip() or quant.get("race_summary", "")
    if ai.get("model_used"):
        summary = f"{summary}（AI：{ai.get('model_used')}）"

    return {
        **quant,
        "mode": "preview",
        "rankings": fused,
        "picks": {"primary": primary, "secondary": secondary, "dark_horse": dark},
        "race_summary": summary,
        "avoid": avoid,
        "ai_enabled": True,
        "ai_model": ai.get("model_used"),
        "ai_provider": ai.get("provider"),
        "ai_confidence": float(ai.get("confidence") or 0.7),
        "ai_blend": {"quant": QUANT_BLEND_WEIGHT, "ai": AI_BLEND_WEIGHT},
    }
