"""Runtime configuration store — allows updating API keys without restart."""
import os
import json
from pathlib import Path
from utils.logger import logger

ENV_FILE = Path(__file__).parent.parent.parent / ".env"

_CONFIG = {}

# --- Auth credentials (runtime only, never persisted) ---
_AUTH_USERNAME = ""
_AUTH_PASSWORD = ""


def set_auth_credentials(username: str, password: str):
    global _AUTH_USERNAME, _AUTH_PASSWORD
    _AUTH_USERNAME = username
    _AUTH_PASSWORD = password


def get_auth_credentials() -> tuple:
    return _AUTH_USERNAME, _AUTH_PASSWORD

ENV_KEY_MAP = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_api_url": "DEEPSEEK_API_URL",
    "qwen_api_key": "QWEN_API_KEY",
    "qwen_api_url": "QWEN_API_URL",
    "glm_api_key": "GLM_API_KEY",
    "glm_api_url": "GLM_API_URL",
    "fallback_api_key": "FALLBACK_LLM_API_KEY",  # deprecated
    "odds_api_key": "ODDS_API_KEY",
    "football_data_api_key": "FOOTBALL_DATA_API_KEY",
}


def load_runtime_config():
    global _CONFIG
    _CONFIG = {
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "deepseek_api_url": os.getenv("DEEPSEEK_API_URL",
                                       "https://api.deepseek.com/v1/chat/completions"),
        "qwen_api_key": os.getenv("QWEN_API_KEY", ""),
        "qwen_api_url": os.getenv("QWEN_API_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
        "glm_api_key": os.getenv("GLM_API_KEY", ""),
        "glm_api_url": os.getenv("GLM_API_URL",
                                  "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
        "fallback_api_key": os.getenv("FALLBACK_LLM_API_KEY", ""),
        "odds_api_key": os.getenv("ODDS_API_KEY", ""),
        "football_data_api_key": os.getenv("FOOTBALL_DATA_API_KEY", ""),
    }
    return _CONFIG


def save_runtime_config(data: dict):
    updates = {}
    for config_key, env_key in ENV_KEY_MAP.items():
        if config_key in data:
            val = data[config_key]
            os.environ[env_key] = val
            _CONFIG[config_key] = val
            updates[env_key] = val

    if not updates:
        return _CONFIG

    # Persist to .env
    try:
        if ENV_FILE.exists():
            lines = ENV_FILE.read_text(encoding="utf-8").split("\n")
        else:
            lines = []

        new_lines = []
        seen = set()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                new_lines.append(line)

        for key, val in updates.items():
            if key not in seen:
                new_lines.append(f"{key}={val}")

        ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        logger.info(f"Runtime config saved: {list(updates.keys())}")
    except Exception as e:
        logger.error(f"Failed to persist config: {e}")

    return _CONFIG


def get_secret(config_key: str) -> str:
    """Return unmasked config value for internal API clients."""
    val = _CONFIG.get(config_key)
    if val:
        return val
    env_key = ENV_KEY_MAP.get(config_key)
    if env_key:
        return os.getenv(env_key, "")
    return ""


def get_runtime_config():
    ds_key = _CONFIG.get("deepseek_api_key", "")
    qw_key = _CONFIG.get("qwen_api_key", "")
    glm_key = _CONFIG.get("glm_api_key", "")
    fb_key = _CONFIG.get("fallback_api_key", "")
    odds_key = _CONFIG.get("odds_api_key", "")
    fd_key = _CONFIG.get("football_data_api_key", "")

    ds_ok = bool(ds_key)
    qw_ok = bool(qw_key)
    glm_ok = bool(glm_key)
    fb_ok = bool(fb_key)

    if ds_ok:
        active = "deepseek"
    elif qw_ok:
        active = "qwen"
    elif glm_ok:
        active = "glm"
    elif fb_ok:
        active = "fallback"
    else:
        active = "rule_engine"

    return {
        "deepseek_api_key": mask_key(ds_key),
        "deepseek_api_url": _CONFIG.get("deepseek_api_url", ""),
        "deepseek_configured": ds_ok,
        "qwen_api_key": mask_key(qw_key),
        "qwen_api_url": _CONFIG.get("qwen_api_url", ""),
        "qwen_configured": qw_ok,
        "glm_api_key": mask_key(glm_key),
        "glm_api_url": _CONFIG.get("glm_api_url", ""),
        "glm_configured": glm_ok,
        "fallback_api_key": mask_key(fb_key),
        "fallback_configured": fb_ok,
        "odds_api_key": mask_key(odds_key),
        "odds_api_configured": bool(odds_key),
        "football_data_api_key": mask_key(fd_key),
        "football_data_configured": bool(fd_key),
        "active_model": active,
        "available_models": [m for m, ok in [
            ("deepseek", ds_ok), ("qwen", qw_ok), ("glm", glm_ok)
        ] if ok] or ["rule_engine"],
    }


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


# Auto-load on import
load_runtime_config()
