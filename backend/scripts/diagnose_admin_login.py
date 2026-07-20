#!/usr/bin/env python3
"""Diagnose admin login issues on the server (run from backend/ with venv active)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext
from sqlalchemy import select

from config import ADMIN_PASSWORD, ADMIN_USERNAME, APP_ENV, DATABASE_URL, IS_PRODUCTION, JWT_SECRET
from db import async_session, init_db
from db.models import User

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main() -> None:
    print("=== Admin login diagnostics ===")
    print(f"APP_ENV: {APP_ENV}")
    print(f"IS_PRODUCTION: {IS_PRODUCTION}")
    print(f"ADMIN_USERNAME: {ADMIN_USERNAME!r}")
    print(f"ADMIN_PASSWORD set: {bool(ADMIN_PASSWORD)} (len={len(ADMIN_PASSWORD or '')})")
    print(f"JWT_SECRET set: {JWT_SECRET not in ('', 'worldcup2026-dev-only-secret')}")
    print(f"DATABASE_URL: {DATABASE_URL}")

    if IS_PRODUCTION and not ADMIN_PASSWORD:
        print("\n[FATAL] APP_ENV=production but ADMIN_PASSWORD is empty — backend should refuse to start.")
    if IS_PRODUCTION and ADMIN_PASSWORD in ("change-me-in-production", "changeme-dev"):
        print("\n[WARN] ADMIN_PASSWORD still looks like a placeholder — login will fail unless DB hash matches.")

    await init_db()
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == ADMIN_USERNAME))
        user = result.scalar_one_or_none()
        if not user:
            print(f"\n[FAIL] No user row for username {ADMIN_USERNAME!r}")
            print("  Fix: restart backend (lifespan creates admin) or run scripts/reset_admin_password.py")
            return
        print(f"\nDB user: id={user.id} is_admin={user.is_admin} is_active={user.is_active}")
        if user.hashed_password:
            match = pwd.verify(ADMIN_PASSWORD or "", user.hashed_password)
            print(f"ADMIN_PASSWORD matches DB hash: {match}")
        else:
            print("DB hashed_password: (empty)")

        others = (await db.execute(select(User).where(User.username != ADMIN_USERNAME))).scalars().all()
        if others:
            print(f"\nOther users in DB: {len(others)} (login must use username {ADMIN_USERNAME!r} for env admin)")


if __name__ == "__main__":
    asyncio.run(main())
