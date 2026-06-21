import json
import os
from typing import Optional
import httpx
from .base_client import BaseLLMClient, PredictionInput, PredictionOutput
from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL
from utils.logger import logger


def _parse_response(data: dict, model_name: str) -> Optional[PredictionOutput]:
    """Parse OpenAI-compatible chat completion response into PredictionOutput."""
    try:
        content = data["choices"][0]["message"]["content"].strip()
        # Handle markdown code block wrapping
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        result = json.loads(content)

        # Parse best_scores: array of 3 scores, or single score fallback
        raw_scores = result.get("best_scores", [])
        if not raw_scores:
            # Backward compat: single best_score field
            raw = result.get("best_score", "?")
            raw_scores = [raw] if raw != "?" else []
        best_scores = [_validate_score(s) for s in raw_scores[:3]]
        best_scores = [s for s in best_scores if s != "?"]
        if not best_scores:
            best_scores = ["?"]

        return PredictionOutput(
            win_rate=float(result["win_rate"]),
            draw_rate=float(result["draw_rate"]),
            lose_rate=float(result["lose_rate"]),
            best_scores=best_scores,
            handicap_result=result.get("handicap_result", "?"),
            total_goals=result.get("total_goals", "?"),
            reason=result.get("reason", ""),
            model_used=model_name,
            confidence=float(result.get("confidence", 0.8))
        )
    except (json.JSONDecodeError, KeyError, ValueError, IndexError) as e:
        logger.error(f"Failed to parse {model_name} response: {e}")
        return None


def _validate_score(score: str) -> str:
    """Validate score format X:Y, cap at realistic World Cup scores."""
    import re
    if not score or score == "?":
        return "?"
    m = re.match(r'^(\d+)[:\-](\d+)$', score.strip())
    if not m:
        return "?"
    a, b = int(m.group(1)), int(m.group(2))
    a = min(a, 6)
    b = min(b, 6)
    if abs(a - b) > 5:
        if a > b:
            a = b + 5
        else:
            b = a + 5
    return f"{a}:{b}"


async def _call_api(api_key: str, base_url: str, model: str, prompt: str,
                    temperature: float = 0.1, max_tokens: int = 500) -> Optional[dict]:
    """Generic OpenAI-compatible API call."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        )
        if resp.status_code >= 400:
            logger.error(f"{model} API error {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        return resp.json()


class DeepSeekClient(BaseLLMClient):

    def __init__(self, api_key: str = None, base_url: str = None):
        self._api_key = api_key
        self._base_url = base_url

    @property
    def api_key(self):
        return self._api_key or os.getenv("DEEPSEEK_API_KEY", "") or DEEPSEEK_API_KEY

    @property
    def base_url(self):
        return self._base_url or os.getenv("DEEPSEEK_API_URL", "") or DEEPSEEK_API_URL

    def model_name(self) -> str:
        return "deepseek-chat"

    async def predict(self, input: PredictionInput) -> Optional[PredictionOutput]:
        if not self.api_key:
            logger.warning("DeepSeek API key not configured")
            return None
        try:
            data = await _call_api(self.api_key, self.base_url, self.model_name(),
                                   self.build_prompt(input))
            return _parse_response(data, self.model_name())
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.error(f"DeepSeek API error: {e}")
            return None


class QwenClient(BaseLLMClient):
    """Alibaba Tongyi Qianwen (通义千问) via DashScope compatible API"""

    DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    DEFAULT_MODEL = "qwen-plus"

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    @property
    def api_key(self):
        return self._api_key or os.getenv("QWEN_API_KEY", "")

    @property
    def base_url(self):
        return self._base_url or os.getenv("QWEN_API_URL", "") or self.DEFAULT_URL

    def model_name(self) -> str:
        return self._model or self.DEFAULT_MODEL

    async def predict(self, input: PredictionInput) -> Optional[PredictionOutput]:
        if not self.api_key:
            logger.warning("Qwen API key not configured")
            return None
        try:
            data = await _call_api(self.api_key, self.base_url, self.model_name(),
                                   self.build_prompt(input))
            return _parse_response(data, self.model_name())
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.error(f"Qwen API error: {e}")
            return None


class GLMClient(BaseLLMClient):
    """Zhipu AI GLM (智谱清言) API"""

    DEFAULT_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    DEFAULT_MODEL = "glm-4-flash"

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    @property
    def api_key(self):
        return self._api_key or os.getenv("GLM_API_KEY", "")

    @property
    def base_url(self):
        return self._base_url or os.getenv("GLM_API_URL", "") or self.DEFAULT_URL

    def model_name(self) -> str:
        return self._model or self.DEFAULT_MODEL

    async def predict(self, input: PredictionInput) -> Optional[PredictionOutput]:
        if not self.api_key:
            logger.warning("GLM API key not configured")
            return None
        try:
            data = await _call_api(self.api_key, self.base_url, self.model_name(),
                                   self.build_prompt(input))
            return _parse_response(data, self.model_name())
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.error(f"GLM API error: {e}")
            return None


# Factory
def create_llm_client(model: str = "deepseek") -> BaseLLMClient:
    if model == "qwen":
        return QwenClient()
    elif model == "glm":
        return GLMClient()
    elif model == "deepseek":
        return DeepSeekClient()
    elif model == "fallback":
        # Backward compat: fallback now uses Qwen
        from config import FALLBACK_LLM_API_KEY
        return QwenClient(api_key=FALLBACK_LLM_API_KEY or os.getenv("QWEN_API_KEY", ""))
    else:
        return DeepSeekClient()
