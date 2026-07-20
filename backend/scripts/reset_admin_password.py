#!/usr/bin/env python3
"""Reset admin password in SQLite to match .env ADMIN_PASSWORD."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext
from sqlalchemy import select

from config import ADMIN_PASSWORD, ADMIN_USERNAME
from db import async_session, init_db
from db.models import User
from db.sqlite_write import commit_session, write_lock

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main() -> None:
    if not ADMIN_PASSWORD:
        print("ERROR: ADMIN_PASSWORD is empty in .env")
        sys.exit(1)
    await init_db()
    async with write_lock:
        async with async_session() as db:
            result = await db.execute(select(User).where(User.username == ADMIN_USERNAME))
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    username=ADMIN_USERNAME,
                    email=f"{ADMIN_USERNAME}@worldcup2026.local",
                    hashed_password=pwd.hash(ADMIN_PASSWORD),
                    is_admin=True,
                    is_active=True,
                )
                db.add(user)
                print(f"Created admin user {ADMIN_USERNAME}")
            else:
                user.hashed_password = pwd.hash(ADMIN_PASSWORD)
                user.is_admin = True
                user.is_active = True
                print(f"Reset password for {ADMIN_USERNAME}")
            await commit_session(db)
    print("Done. Restart backend not required if only DB was wrong.")


if __name__ == "__main__":
    asyncio.run(main())
