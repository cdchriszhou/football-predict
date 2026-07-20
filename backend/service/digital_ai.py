"""数字彩多模型 AI 精选：DeepSeek / 通义千问 / 智谱 GLM 并行参考并融合。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from llm.deepseek_client import _call_api, _parse_llm_json, create_llm_client
from utils.logger import logger

MODEL_LABELS = {
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "glm": "GLM",
}

# 推荐结果短缓存：切 Tab 回访可秒开；AI 结果尤其贵
_REC_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_REC_CACHE_TTL_SEC = 180


def rec_cache_get(key: str) -> dict[str, Any] | None:
    hit = _REC_CACHE.get(key)
    if not hit:
        return None
    ts, payload = hit
    if time.monotonic() - ts > _REC_CACHE_TTL_SEC:
        _REC_CACHE.pop(key, None)
        return None
    # 返回浅拷贝，避免调用方改写缓存
    return dict(payload)


def rec_cache_set(key: str, payload: dict[str, Any]) -> None:
    _REC_CACHE[key] = (time.monotonic(), dict(payload))


def configured_digital_models() -> list[str]:
    from service.prediction_service import get_configured_models

    return get_configured_models()


def model_display_name(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id)


async def _call_one_model(model_id: str, prompt: str, timeout_sec: float = 12.0) -> dict[str, Any] | None:
    client = create_llm_client(model_id)
    if not getattr(client, "api_key", ""):
        return None
    try:
        data = await asyncio.wait_for(
            _call_api(
                client.api_key,
                client.base_url,
                client.model_name(),
                prompt,
                temperature=0.4,
                max_tokens=800,
                json_mode=True,
            ),
            timeout=timeout_sec,
        )
        content = (data or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_llm_json(content)
        if not isinstance(parsed, dict):
            return None
        return {"model": model_id, "parsed": parsed}
    except asyncio.TimeoutError:
        logger.warning("digital AI timeout [%s] after %.0fs", model_id, timeout_sec)
        return None
    except Exception as e:
        logger.warning("digital AI call failed [%s]: %s", model_id, e)
        return None


async def gather_digital_llm_json(prompt: str) -> list[dict[str, Any]]:
    """并行调用已配置的 DeepSeek / Qwen / GLM，返回成功解析的结果列表。"""
    models = configured_digital_models()
    if not models:
        return []
    results = await asyncio.gather(*[_call_one_model(m, prompt) for m in models])
    return [r for r in results if r]


def fuse_ai_picks(
    model_results: list[dict[str, Any]],
    *,
    extract_items: Callable[[dict[str, Any]], list[dict]],
    validate_item: Callable[[dict], Any | None],
    build_rec: Callable[[Any, float, str, list[str]], dict],
    limit: int = 3,
) -> list[dict]:
    """
    多模型 picks 融合：
    - 同一注被多个模型给出时提升排序与置信度
    - 保留贡献模型名，便于前端展示
    """
    buckets: dict[tuple, dict[str, Any]] = {}

    for result in model_results:
        model_id = result.get("model") or "ai"
        parsed = result.get("parsed") or {}
        summary = str(parsed.get("summary") or "").strip()
        items = extract_items(parsed)
        for item in items:
            if not isinstance(item, dict):
                continue
            validated = validate_item(item)
            if not validated:
                continue
            if isinstance(validated, tuple) and len(validated) == 2 and isinstance(validated[0], list):
                # ssq: (reds, blue)
                key = tuple(validated[0] + [validated[1]])
            else:
                key = tuple(validated)

            try:
                conf = float(item.get("confidence", 0.6))
            except (TypeError, ValueError):
                conf = 0.6
            conf = max(0.0, min(1.0, conf))
            reason = str(item.get("reason") or summary or "AI 结合频率与走势精选").strip()[:120]

            bucket = buckets.get(key)
            if not bucket:
                buckets[key] = {
                    "validated": validated,
                    "votes": [conf],
                    "reasons": [reason],
                    "models": [model_id],
                }
            else:
                if model_id not in bucket["models"]:
                    bucket["models"].append(model_id)
                bucket["votes"].append(conf)
                if reason and reason not in bucket["reasons"]:
                    bucket["reasons"].append(reason)

    ranked = sorted(
        buckets.values(),
        key=lambda b: (
            -len(b["models"]),
            -sum(b["votes"]) / max(1, len(b["votes"])),
        ),
    )

    out: list[dict] = []
    for i, bucket in enumerate(ranked[:limit]):
        models = bucket["models"]
        avg_conf = sum(bucket["votes"]) / max(1, len(bucket["votes"]))
        # 多模型共识略抬升置信度
        if len(models) >= 2:
            avg_conf = min(1.0, avg_conf + 0.08 * (len(models) - 1))
        reason = bucket["reasons"][0]
        if len(models) >= 2:
            labels = "+".join(model_display_name(m) for m in models)
            reason = f"多模型共识（{labels}）：{reason}"[:120]
        else:
            reason = f"[{model_display_name(models[0])}] {reason}"[:120]
        rec = build_rec(bucket["validated"], round(avg_conf, 4), reason, models)
        rec["id"] = f"ai-{i + 1}"
        rec["source"] = "ai"
        rec["models"] = models
        rec["model_label"] = "+".join(model_display_name(m) for m in models)
        out.append(rec)
    return out
