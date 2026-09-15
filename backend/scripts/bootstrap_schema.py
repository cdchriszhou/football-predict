#!/usr/bin/env python3
"""Bootstrap DB schema for deploy: create_all then alembic upgrade head.

Matches the order used by ``db.init_db()``, but exits non-zero if Alembic fails
so ``update.sh`` can surface the error. Safe on fresh installs (empty DB).
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


async def _create_all() -> None:
    import db.models  # noqa: F401 — register metadata
    from db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> int:
    asyncio.run(_create_all())
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_BACKEND),
    )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
