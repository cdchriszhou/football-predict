"""User access entitlement checks for competitions and account expiry."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from db.models import User

ACCESS_DENIED_COMPETITION_MSG = "请购买访问该赛事的权益！ 199元/月"
ACCESS_DENIED_EXPIRED_MSG = "您的账户访问权限已过期，请联系管理员续期"
ACCESS_DENIED_SPORTTERY_MSG = "您暂无体彩购买方案访问权限，请联系管理员开通"


def parse_allowed_competitions(raw: str | None) -> list[str] | None:
    """Return None when all competitions are allowed."""
    if raw is None or raw == "":
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, list):
        return None
    if not data or "*" in data:
        return None
    return [str(x) for x in data if x]


def serialize_allowed_competitions(slugs: list[str] | None) -> str | None:
    if slugs is None:
        return None
    cleaned = [s for s in slugs if s and s != "*"]
    return json.dumps(cleaned, ensure_ascii=False)


def user_access_payload(user: User | None, *, is_admin: bool = False) -> dict:
    if is_admin and not user:
        return {
            "access_expires_at": None,
            "allowed_competitions": None,
            "has_all_competitions": True,
            "account_expired": False,
            "can_access_sporttery": True,
        }
    if not user:
        return {
            "access_expires_at": None,
            "allowed_competitions": None,
            "has_all_competitions": True,
            "account_expired": False,
            "can_access_sporttery": True,
        }
    allowed = parse_allowed_competitions(user.allowed_competitions)
    expired = bool(
        user.access_expires_at and datetime.utcnow() > user.access_expires_at
    )
    sporttery = bool(user.is_admin or user.can_access_sporttery)
    return {
        "access_expires_at": user.access_expires_at.isoformat() if user.access_expires_at else None,
        "allowed_competitions": allowed,
        "has_all_competitions": allowed is None,
        "account_expired": expired,
        "can_access_sporttery": sporttery,
    }


def check_sporttery_access(
    user: User | None,
    *,
    is_admin: bool = False,
) -> tuple[bool, str | None]:
    if is_admin:
        return True, None
    if not user:
        return False, ACCESS_DENIED_SPORTTERY_MSG
    if user.is_admin:
        return True, None
    if user.can_access_sporttery:
        return True, None
    return False, ACCESS_DENIED_SPORTTERY_MSG


def check_competition_access(
    user: User | None,
    competition_slug: str,
    *,
    is_admin: bool = False,
) -> tuple[bool, str | None]:
    if is_admin:
        return True, None
    if not user:
        return True, None
    if user.is_admin:
        return True, None
    if user.access_expires_at and datetime.utcnow() > user.access_expires_at:
        return False, ACCESS_DENIED_EXPIRED_MSG
    allowed = parse_allowed_competitions(user.allowed_competitions)
    if allowed is None:
        return True, None
    if competition_slug in allowed:
        return True, None
    return False, ACCESS_DENIED_COMPETITION_MSG


def can_access_competition(
    access_expires_at: str | None,
    allowed_competitions: list[str] | None,
    competition_slug: str,
    *,
    is_admin: bool = False,
    has_all_competitions: bool = True,
    account_expired: bool = False,
) -> tuple[bool, str | None]:
    if is_admin:
        return True, None
    if account_expired:
        return False, ACCESS_DENIED_EXPIRED_MSG
    if access_expires_at:
        try:
            exp = datetime.fromisoformat(access_expires_at.replace("Z", "+00:00"))
            if exp.tzinfo:
                exp = exp.replace(tzinfo=None)
            if datetime.utcnow() > exp:
                return False, ACCESS_DENIED_EXPIRED_MSG
        except ValueError:
            pass
    if has_all_competitions or allowed_competitions is None:
        return True, None
    if competition_slug in (allowed_competitions or []):
        return True, None
    return False, ACCESS_DENIED_COMPETITION_MSG
