from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from db.redis_client import cache_get, cache_set
from service.tournament_service import (
    TournamentPrediction,
    TournamentPredictionService,
    _apply_knockout_constraints,
    resolve_knockout_progress,
)
from utils.response import success
from utils.logger import logger
from api.auth import get_current_user
from api.deps import require_competition_entitlement

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])
tournament_service = TournamentPredictionService()


def _dict_to_prediction(data: dict) -> TournamentPrediction:
    return TournamentPrediction(
        champion=data.get("champion", "?"),
        runner_up=data.get("runner_up", "?"),
        semifinalists=list(data.get("semifinalists") or []),
        reason=data.get("reason", ""),
        model_used=data.get("model_used", ""),
        confidence=float(data.get("confidence") or 0.7),
    )


@router.get("/predictions")
async def get_tournament_predictions(
    model: str = Query("auto", description="auto / deepseek / qwen / glm"),
    refresh: bool = Query(False, description="skip cache"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Get AI-powered tournament predictions (champion, runner-up, semifinalists)."""
    cache_key = f"tournament:prediction:{model}"
    result = None

    if not refresh:
        cached = await cache_get(cache_key)
        if cached:
            result = cached

    if result is None:
        try:
            result = await tournament_service.predict_tournament(db, model)
        except Exception as e:
            logger.error(f"Tournament prediction failed: {e}")
            return success({
                "champion": "?", "runner_up": "?",
                "semifinalists": [], "reason": f"预测服务异常: {e}",
                "model_used": "error", "confidence": 0
            })
        # Cache for 1 hour (knockout lock re-applied on every read below)
        await cache_set(cache_key, result, ttl=3600)

    # Always re-apply schedule locks so stale cache cannot show eliminated teams
    try:
        progress = await resolve_knockout_progress(db)
        locked = _apply_knockout_constraints(_dict_to_prediction(result), progress)
        result = locked.to_dict()
        if progress.get("notes"):
            result["knockout_locked"] = True
            result["knockout_notes"] = progress["notes"]
    except Exception as e:
        logger.warning(f"Failed to re-apply knockout constraints: {e}")

    return success(result)
