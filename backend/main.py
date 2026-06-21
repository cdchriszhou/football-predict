from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
from config import CORS_ORIGINS, CORS_ALLOW_ORIGIN_REGEX, HOST, PORT, ADMIN_USERNAME, ADMIN_PASSWORD
from db import init_db, close_db
from db.redis_client import init_redis, close_redis
from utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting 2026 World Cup Predictor...")

    from service.runtime_config import set_auth_credentials
    set_auth_credentials(ADMIN_USERNAME, ADMIN_PASSWORD)
    logger.info("Admin account: %s (password from ADMIN_PASSWORD env)", ADMIN_USERNAME)

    try:
        await init_db()
        from db.models import User
        from db import async_session
        from db.sqlite_write import commit_session, write_lock
        from passlib.context import CryptContext
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        async with write_lock:
            async with async_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(User).where(User.username == ADMIN_USERNAME)
                )
                admin_user = result.scalar_one_or_none()
                if not admin_user:
                    session.add(User(
                        username=ADMIN_USERNAME,
                        email=f"{ADMIN_USERNAME}@worldcup2026.local",
                        hashed_password=pwd_ctx.hash(ADMIN_PASSWORD),
                        is_admin=True,
                        is_active=True,
                    ))
                    await commit_session(session)
                    logger.info("Default admin user created in database")
                elif not pwd_ctx.verify(ADMIN_PASSWORD, admin_user.hashed_password):
                    admin_user.hashed_password = pwd_ctx.hash(ADMIN_PASSWORD)
                    admin_user.is_admin = True
                    admin_user.is_active = True
                    await commit_session(session)
                    logger.info(
                        "Admin user %s password synced from .env (is_admin=%s)",
                        ADMIN_USERNAME,
                        admin_user.is_admin,
                    )
        # 五大联赛：启动时仅做轻量种子（不阻塞 football-data 全量同步）
        from data.competitions import COMPETITIONS
        from data.league_seed import ensure_league_data
        async with write_lock:
            async with async_session() as session:
                for slug, comp in COMPETITIONS.items():
                    if comp.get("type") != "club":
                        continue
                    try:
                        result = await ensure_league_data(session, slug)
                        if result.get("teams") or result.get("fixtures"):
                            logger.info(f"League seed [{slug}]: {result}")
                    except Exception as e:
                        logger.warning(f"League seed [{slug}] failed: {e}")
                await commit_session(session)
        # 世界杯：启动时同步已确认赛果，避免已结束比赛缺比分
        from data.match_status import maintain_competition_matches
        from crawler.worldcup_score_sync import refresh_fd_cache
        async with write_lock:
            async with async_session() as session:
                try:
                    await refresh_fd_cache()
                    wc = await maintain_competition_matches(session, "worldcup-2026")
                    if any(wc.values()):
                        logger.info(f"World Cup match maintenance on startup: {wc}")
                    await commit_session(session)
                except Exception as e:
                    logger.warning(f"World Cup match maintenance on startup failed: {e}")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
    try:
        await init_redis()
    except Exception as e:
        logger.error(f"Redis init failed: {e}")
    try:
        from scheduler.jobs import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler start failed: {e}")
    logger.info("System ready (some services may be degraded)")
    yield
    try:
        from scheduler.jobs import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    try:
        await close_redis()
    except Exception:
        pass
    try:
        await close_db()
    except Exception:
        pass
    logger.info("System shutdown complete")


app = FastAPI(
    title="2026 World Cup Predictor",
    version="1.0.0",
    lifespan=lifespan
)

_cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if CORS_ALLOW_ORIGIN_REGEX:
    _cors_kwargs["allow_origin_regex"] = CORS_ALLOW_ORIGIN_REGEX
    _cors_kwargs["allow_origins"] = []
else:
    _cors_kwargs["allow_origins"] = CORS_ORIGINS
app.add_middleware(CORSMiddleware, **_cors_kwargs)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "data": None,
                "timestamp": 0,
            },
        )
    logger.exception(f"Unhandled API error: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": str(exc), "data": None, "timestamp": 0},
    )


# Register routers
from api.matches import router as matches_router
from api.teams import router as teams_router
from api.predictions import router as predictions_router
from api.odds import router as odds_router
from api.admin import router as admin_router
from api.auth import router as auth_router
from api.tournament import router as tournament_router
from api.data import router as data_router
from api.competitions import router as competitions_router
from api.sporttery import router as sporttery_router
from api.hkjc import router as hkjc_router

app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(competitions_router, prefix="/api/v1/competitions", tags=["赛事"])
app.include_router(matches_router, prefix="/api/v1/matches", tags=["赛程"])
app.include_router(teams_router, prefix="/api/v1/teams", tags=["球队"])
app.include_router(predictions_router, prefix="/api/v1/predictions", tags=["预测"])
app.include_router(odds_router, prefix="/api/v1/odds", tags=["盘口"])
app.include_router(sporttery_router, prefix="/api/v1/sporttery", tags=["体彩方案"])
app.include_router(hkjc_router, prefix="/api/v1/hkjc", tags=["香港赛马"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["管理"])
app.include_router(tournament_router, prefix="/api/v1/tournament", tags=["赛事预测"])
app.include_router(data_router, prefix="/api/v1/data", tags=["数据"])


@app.get("/")
async def root():
    return {"name": "2026 World Cup Predictor", "version": "1.0.0", "status": "running"}


# ── SPA static files & fallback (production) ───────────────────

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
INDEX_HTML = os.path.join(FRONTEND_DIST, "index.html")

if os.path.isdir(FRONTEND_DIST):
    _ROOT_FILES = frozenset([
        "manifest.webmanifest", "registerSW.js", "sw.js",
        "workbox-e4022e15.js", "worldcup2026-logo.svg", "worldcup2026-logo.png",
    ])

    @app.get("/{filename:path}", include_in_schema=False)
    async def serve_frontend(filename: str):
        # API routes are already handled by the routers registered above.
        if filename.startswith("api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        # Serve hashed assets from dist/assets/
        if filename.startswith("assets/"):
            filepath = os.path.join(FRONTEND_DIST, filename)
            if os.path.isfile(filepath):
                return FileResponse(filepath)
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        # Serve root-level static files
        if filename in _ROOT_FILES:
            filepath = os.path.join(FRONTEND_DIST, filename)
            if os.path.isfile(filepath):
                return FileResponse(filepath)

        # Everything else is a frontend route — serve index.html (SPA fallback)
        if os.path.isfile(INDEX_HTML):
            return FileResponse(INDEX_HTML)

        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not Found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
