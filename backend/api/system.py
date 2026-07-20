"""Public system endpoints (no auth) — production health probes."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from db.models import Match
from db.redis_client import cache_mode, get_redis
from utils.response import success

router = APIRouter()


@router.get("/health")
async def public_health(db: AsyncSession = Depends(get_db)):
    """Unauthenticated health — for prod proxy checks and admin dashboard."""
    db_status = "error"
    match_count = 0
    try:
        ok = (await db.execute(text("SELECT 1"))).scalar() == 1
        if ok:
            db_status = "ok"
            match_count = (await db.execute(select(func.count(Match.id)))).scalar() or 0
    except Exception:
        db_status = "error"

    redis = await get_redis()
    if redis is not None:
        try:
            await redis.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "memory"
    else:
        mode = cache_mode()
        redis_status = "memory" if mode == "memory" else "unavailable"

    from service.runtime_config import get_runtime_config

    cfg = get_runtime_config()
    ai_configured = bool(
        cfg.get("deepseek_configured")
        or cfg.get("qwen_configured")
        or cfg.get("glm_configured")
        or cfg.get("fallback_configured")
    )

    return success({
        "database": db_status,
        "redis": redis_status,
        "ai_configured": ai_configured,
        "active_model": cfg.get("active_model", "rule_engine"),
        "match_count": match_count,
        "status": "running" if db_status == "ok" else "degraded",
    })
