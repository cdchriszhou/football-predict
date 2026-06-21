from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from db.redis_client import cache_get, cache_set
from service.tournament_service import TournamentPredictionService
from utils.response import success
from utils.logger import logger
from api.auth import get_current_user
from api.deps import require_competition_entitlement

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])
tournament_service = TournamentPredictionService()


@router.get("/predictions")
async def get_tournament_predictions(
    model: str = Query("auto", description="auto / deepseek / qwen / glm"),
    refresh: bool = Query(False, description="skip cache"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Get AI-powered tournament predictions (champion, runner-up, semifinalists)."""
    cache_key = f"tournament:prediction:{model}"

    if not refresh:
        cached = await cache_get(cache_key)
        if cached:
            return success(cached)

    try:
        result = await tournament_service.predict_tournament(db, model)
    except Exception as e:
        logger.error(f"Tournament prediction failed: {e}")
        return success({
            "champion": "?", "runner_up": "?",
            "semifinalists": [], "reason": f"预测服务异常: {e}",
            "model_used": "error", "confidence": 0
        })

    # Cache for 1 hour
    await cache_set(cache_key, result, ttl=3600)

    return success(result)
