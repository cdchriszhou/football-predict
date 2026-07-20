# -*- coding: utf-8 -*-
"""Production connectivity diagnostic — run on the server."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)


async def main():
    from config import (
        APP_ENV, DATABASE_URL, IS_PRODUCTION, JWT_SECRET, ADMIN_PASSWORD,
        REDIS_URL, DEEPSEEK_API_KEY, QWEN_API_KEY, GLM_API_KEY,
    )

    print("=== Production diagnostic ===")
    print(f"APP_ENV: {APP_ENV}")
    print(f"DATABASE_URL: {DATABASE_URL}")
    db_path = Path(DATABASE_URL.split("///")[-1])
    print(f"DB file exists: {db_path.is_file()} size={db_path.stat().st_size if db_path.is_file() else 0}")

    if IS_PRODUCTION:
        if not ADMIN_PASSWORD or ADMIN_PASSWORD == "change-me-in-production":
            print("[FAIL] ADMIN_PASSWORD not configured for production")
        if JWT_SECRET in ("", "change-me-in-production", "worldcup2026-dev-only-secret"):
            print("[FAIL] JWT_SECRET not configured for production")

    # DB
    try:
        from db import async_session, init_db
        from sqlalchemy import func, select, text
        from db.models import Match
        await init_db()
        async with async_session() as s:
            n = (await s.execute(select(func.count(Match.id)))).scalar()
            ok = (await s.execute(text("SELECT 1"))).scalar()
        print(f"[OK] Database: SELECT 1={ok}, matches={n}")
        if n == 0:
            print("[WARN] No matches in DB — dashboard will be empty until crawler runs")
    except Exception as e:
        print(f"[FAIL] Database: {e}")

    # Redis
    try:
        from db.redis_client import init_redis, cache_mode, close_redis
        await init_redis()
        print(f"[OK] Redis/cache mode: {cache_mode()} url={REDIS_URL}")
        await close_redis()
    except Exception as e:
        print(f"[WARN] Redis: {e} (in-memory fallback is OK)")

    # AI keys
    keys = {
        "DEEPSEEK": bool(DEEPSEEK_API_KEY),
        "QWEN": bool(QWEN_API_KEY),
        "GLM": bool(GLM_API_KEY),
    }
    if any(keys.values()):
        print(f"[OK] LLM keys configured: {keys}")
    else:
        print(f"[WARN] No LLM API keys — predictions use rule_engine only: {keys}")

    # HTTP health (if backend running)
    try:
        import urllib.request
        url = "http://127.0.0.1:8888/api/v1/system/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = json.loads(resp.read().decode())
        print(f"[OK] HTTP {url}: {body.get('data')}")
    except Exception as e:
        print(f"[FAIL] Backend HTTP not reachable on :8888 — {e}")
        print("       Run ./start-prod.sh and check backend.log")

    print("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
