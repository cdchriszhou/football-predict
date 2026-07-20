"""Shared API dependencies."""
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_db_user, verify_token
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from api.competitions import resolve_competition
from db import get_db
from service.user_access import check_competition_access

_security = HTTPBearer()


async def require_competition_entitlement(
    competition: str = Query("worldcup-2026"),
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Block API access when user lacks entitlement for the requested competition."""
    payload = verify_token(credentials.credentials)
    username = payload.get("sub")
    is_admin = bool(payload.get("adm"))
    user = await get_db_user(db, username=username) if username else None
    if user and user.is_admin:
        is_admin = True

    slug = resolve_competition(competition)
    ok, message = check_competition_access(user, slug, is_admin=is_admin)
    if not ok:
        raise HTTPException(status_code=403, detail=message)
    return slug
