from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from passlib.context import CryptContext
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_RESET_EXPIRE_MINUTES
from db import get_db
from db.models import User
from utils.response import success, error
from service.user_access import user_access_payload
import logging

logger = logging.getLogger("worldcup.auth")

router = APIRouter()
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Pydantic models ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    invite_code: str


class VerifyInviteRequest(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Token helpers ─────────────────────────────────────────────────

def create_access_token(username: str, user_id: int = None, is_admin: bool = False) -> str:
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "iat": datetime.utcnow(),
        "exp": expire,
    }
    if user_id is not None:
        payload["uid"] = user_id
    if is_admin:
        payload["adm"] = True
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_reset_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=JWT_RESET_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "purpose": "password_reset",
        "iat": datetime.utcnow(),
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_reset_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "password_reset":
            return None
        return int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    payload = verify_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )
    return username


async def get_current_admin_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> str:
    payload = verify_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )
    if payload.get("adm"):
        return username
    user = await get_db_user(db, username=username)
    if not user or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return username


# ── Helper: get DB user ───────────────────────────────────────────

async def get_db_user(db: AsyncSession, username: str = None, email: str = None):
    if username:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    if email:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    return None


# ── Auth endpoints ────────────────────────────────────────────────

@router.post("/verify-invite")
async def verify_invite(req: VerifyInviteRequest, db: AsyncSession = Depends(get_db)):
    from db.models import InviteCode
    result = await db.execute(
        select(InviteCode).where(InviteCode.code == req.code)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        return error(400, "邀请码无效")
    if invite.expires_at < datetime.utcnow():
        return error(400, "邀请码已过期")
    return success({"code": invite.code}, "邀请码有效")


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    from db.models import InviteCode

    if len(req.username) < 3 or len(req.username) > 50:
        return error(400, "用户名长度需在 3-50 个字符之间")
    if len(req.password) < 6:
        return error(400, "密码长度不能少于 6 个字符")

    # Validate invite code
    result = await db.execute(
        select(InviteCode).where(InviteCode.code == req.invite_code)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        return error(400, "邀请码无效")
    if invite.expires_at < datetime.utcnow():
        return error(400, "邀请码已过期")

    existing = await get_db_user(db, username=req.username)
    if existing:
        return error(409, "用户名已被注册")

    if "@" in req.email:
        existing_email = await get_db_user(db, email=req.email)
        if existing_email:
            return error(409, "邮箱已被注册")

    # Increment invite code usage count (multi-use support)
    invite.use_count += 1

    hashed = pwd_context.hash(req.password)
    new_user = User(
        username=req.username,
        email=req.email,
        hashed_password=hashed,
        is_admin=False,
        is_active=True,
        can_access_sporttery=False,
    )
    db.add(new_user)
    await db.commit()

    logger.info(f"New user registered: {req.username} (invite: {req.invite_code}, use_count: {invite.use_count})")
    token = create_access_token(req.username)
    return success({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_HOURS * 3600,
        "username": req.username,
        **user_access_payload(new_user),
    }, "注册成功")


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_db_user(db, username=req.username)

    if user and not user.is_active:
        logger.warning("Login rejected: user %s is inactive", req.username)
    elif user and user.is_active and pwd_context.verify(req.password, user.hashed_password):
        user.last_login_at = datetime.utcnow()
        await db.commit()
        token = create_access_token(user.username, user.id, is_admin=user.is_admin)
        access = user_access_payload(user, is_admin=user.is_admin)
        return success({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": JWT_EXPIRE_HOURS * 3600,
            "username": user.username,
            "is_admin": user.is_admin,
            **access,
        }, "登录成功")

    # Fallback: check in-memory admin credentials (backward compat)
    from service.runtime_config import get_auth_credentials
    stored_user, stored_pass = get_auth_credentials()
    if stored_user and req.username == stored_user and req.password == stored_pass:
        db_user = await get_db_user(db, username=stored_user)
        if db_user:
            db_user.last_login_at = datetime.utcnow()
            await db.commit()
        token = create_access_token(req.username, is_admin=True)
        return success({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": JWT_EXPIRE_HOURS * 3600,
            "username": stored_user,
            "is_admin": True,
            **user_access_payload(db_user, is_admin=True),
        }, "登录成功")

    if user and user.is_active:
        logger.warning("Login failed: wrong password for user %s", req.username)
    elif user:
        logger.warning("Login failed: user %s inactive", req.username)
    else:
        from service.runtime_config import get_auth_credentials
        stored_user, _ = get_auth_credentials()
        if req.username != stored_user:
            logger.warning("Login failed: unknown username %r (env admin is %r)", req.username, stored_user)
    return error(401, "用户名或密码错误")


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await get_db_user(db, email=req.email)
    if not user:
        # Don't reveal whether email exists
        return success(None, "如果该邮箱已注册，重置链接将发送到您的邮箱")

    reset_token = create_reset_token(user.id)
    user.reset_token = reset_token
    user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=JWT_RESET_EXPIRE_MINUTES)
    await db.commit()

    logger.info("Password reset requested for user id=%s", user.id)
    return success(None, f"如果该邮箱已注册，重置链接将发送到您的邮箱（有效期 {JWT_RESET_EXPIRE_MINUTES} 分钟）")


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    user_id = verify_reset_token(req.token)
    if not user_id:
        return error(400, "无效或已过期的重置令牌")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error(400, "用户不存在")
    if user.reset_token != req.token:
        return error(400, "令牌已被使用或无效")
    if user.reset_token_expiry and user.reset_token_expiry < datetime.utcnow():
        return error(400, "重置令牌已过期")

    if len(req.new_password) < 6:
        return error(400, "密码长度不能少于 6 个字符")

    user.hashed_password = pwd_context.hash(req.new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    await db.commit()

    logger.info(f"Password reset for user: {user.username}")
    return success(None, "密码重置成功，请使用新密码登录")


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if len(req.new_password) < 6:
        return error(400, "密码长度不能少于 6 个字符")
    if req.old_password == req.new_password:
        return error(400, "新密码不能与旧密码相同")

    user = await get_db_user(db, username=current_user)
    if not user:
        # Fallback: in-memory admin can't change password
        return error(400, "当前账号不支持修改密码")

    if not pwd_context.verify(req.old_password, user.hashed_password):
        return error(400, "旧密码错误")

    user.hashed_password = pwd_context.hash(req.new_password)
    await db.commit()
    logger.info(f"Password changed for user: {user.username}")
    return success(None, "密码修改成功")


@router.get("/me")
async def get_me(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await get_db_user(db, username=current_user)
    if user:
        return success({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            **user_access_payload(user, is_admin=user.is_admin),
        })
    return success({
        "username": current_user,
        "is_admin": True,
        **user_access_payload(None, is_admin=True),
    })
