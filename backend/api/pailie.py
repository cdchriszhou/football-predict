from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, get_db_user, verify_token
from db import get_db
from service.pailie_service import get_draw_history, get_games_catalog, get_recommendations
from service.user_access import check_competition_access
from utils.response import success

router = APIRouter()
_security = HTTPBearer()

PAILIE_SLUG = "pailie"


async def _require_pailie_access(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> str:
    payload = verify_token(credentials.credentials)
    username = payload.get("sub")
    is_admin = bool(payload.get("adm"))
    user = await get_db_user(db, username=username) if username else None
    if user and user.is_admin:
        is_admin = True
    ok, message = check_competition_access(user, PAILIE_SLUG, is_admin=is_admin)
    if not ok:
        raise HTTPException(status_code=403, detail=message)
    return PAILIE_SLUG


@router.get("/catalog")
async def pailie_catalog(
    _slug: str = Depends(_require_pailie_access),
    current_user: str = Depends(get_current_user),
):
    return success(get_games_catalog())


@router.get("/history")
async def pailie_history(
    game: str | None = Query(None, description="pl3 | pl5，缺省返回两者"),
    limit: int = Query(15, ge=1, le=50),
    _slug: str = Depends(_require_pailie_access),
    current_user: str = Depends(get_current_user),
):
    data = await get_draw_history(game, limit)
    return success(data)


@router.get("/recommend")
async def pailie_recommend(
    game: str = Query("pl3", description="pl3 | pl5 | qxc"),
    window: int = Query(100, ge=20, le=200, description="统计近 N 期开奖"),
    use_ai: bool = Query(True, description="是否启用 AI 精选（需配置 DEEPSEEK_API_KEY）"),
    _slug: str = Depends(_require_pailie_access),
    current_user: str = Depends(get_current_user),
):
    data = await get_recommendations(game, window, use_ai=use_ai)
    return success(data)
