from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, get_db_user, verify_token
from api.competitions import resolve_competition
from api.deps import require_competition_entitlement
from db import get_db
from service.sporttery_plan_service import get_today_sporttery_plan
from service.user_access import check_sporttery_access
from utils.response import success

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])
_security = HTTPBearer()


@router.get("/plan/today")
async def get_today_plan(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    user = await get_db_user(db, username=current_user)
    payload = verify_token(credentials.credentials)
    is_admin = bool(payload.get("adm")) or (user and user.is_admin)
    ok, message = check_sporttery_access(user, is_admin=is_admin)
    if not ok:
        raise HTTPException(status_code=403, detail=message)

    comp_slug = resolve_competition(competition)
    data = await get_today_sporttery_plan(db, comp_slug)
    return success(data)
