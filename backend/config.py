import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

# backend/ is usually the process cwd; project .env lives one level up.
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
for _env_path in (_PROJECT_ROOT / ".env", _BACKEND_DIR / ".env"):
    if _env_path.is_file():
        load_dotenv(_env_path, override=True)

APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"

# Database — SQLite for single-node deployment
_BASE_DIR = str(_BACKEND_DIR)
_DB_PATH = os.path.join(_BASE_DIR, "worldcup2026.db")
DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Admin credentials
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    if IS_PRODUCTION:
        raise RuntimeError("ADMIN_PASSWORD must be set when APP_ENV=production")
    ADMIN_PASSWORD = "changeme-dev"
    warnings.warn("ADMIN_PASSWORD not set — using dev default 'changeme-dev'", stacklevel=1)

# LLM — multi-model support
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
FALLBACK_LLM_API_KEY = os.getenv("FALLBACK_LLM_API_KEY", "")

# JWT
_DEFAULT_JWT = "worldcup2026-dev-only-secret"
JWT_SECRET = os.getenv("JWT_SECRET", _DEFAULT_JWT)
if JWT_SECRET == _DEFAULT_JWT and IS_PRODUCTION:
    raise RuntimeError("JWT_SECRET must be set to a strong random value when APP_ENV=production")
if JWT_SECRET == _DEFAULT_JWT:
    warnings.warn("Using default JWT_SECRET — not safe for production", stacklevel=1)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
JWT_RESET_EXPIRE_MINUTES = 30

# Crawler
CRAWLER_PROXY = os.getenv("CRAWLER_PROXY", None)
# Sporttery.cn: leave empty on **China-hosted** servers (direct works). Set only on overseas VPS.
SPORTTERY_PROXY = (os.getenv("SPORTTERY_PROXY") or "").strip() or None
# Force direct for sporttery (ignore SPORTTERY_PROXY / CRAWLER_PROXY). Recommended for domestic deploy.
SPORTTERY_DIRECT = os.getenv("SPORTTERY_DIRECT", "").lower() in ("1", "true", "yes")
# Fallback to real Chromium when httpx gets WAF 567 (needs: playwright install chromium)
SPORTTERY_PLAYWRIGHT_FALLBACK = os.getenv("SPORTTERY_PLAYWRIGHT_FALLBACK", "true").lower() in (
    "1", "true", "yes",
)
CRAWLER_INTERVAL_HOURS = 6

# Real bookmaker odds (The Odds API)
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

# Server
HOST = "0.0.0.0"
PORT = 8888
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    CORS_ORIGINS = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:4173",
    ]
# Production LAN / reverse-proxy: allow any http(s) origin when not explicitly configured.
CORS_ALLOW_ORIGIN_REGEX = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
if not CORS_ALLOW_ORIGIN_REGEX and IS_PRODUCTION and not _cors_env:
    CORS_ALLOW_ORIGIN_REGEX = r"https?://.*"
