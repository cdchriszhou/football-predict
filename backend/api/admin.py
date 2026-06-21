from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from db.models import CrawlerLog, InviteCode, User
from crawler import run_all_crawlers, run_schedule_crawler, run_team_crawler, run_all_odds_crawlers
from crawler.league_crawler import run_league_crawler
from service.prediction_service import PredictionService, team_to_dict, prepare_fused_odds
from service.calibration_service import CalibratedRuleEngine, run_backtest, calibrate, load_calibrated_params
from service.runtime_config import get_runtime_config, save_runtime_config
from utils.response import success, error
from utils.logger import logger
from utils.datetime_helpers import utc_now, format_utc_iso
from api.auth import get_current_admin_user
from data.competitions import list_competitions, is_valid_competition
from service.user_access import parse_allowed_competitions, serialize_allowed_competitions
from service.runtime_logs import tail_log_file, LOG_SOURCES
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values


class ConfigRequest(BaseModel):
    deepseek_api_key: str = None
    deepseek_api_url: str = None
    qwen_api_key: str = None
    qwen_api_url: str = None
    glm_api_key: str = None
    glm_api_url: str = None
    fallback_api_key: str = None
    odds_api_key: str = None  # deprecated
    football_data_api_key: str = None


router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_admin_user)):
    try:
        from sqlalchemy import text
        from db.redis_client import get_redis, cache_mode
        db_ok = (await db.execute(text("SELECT 1"))).scalar() == 1

        redis = await get_redis()
        if redis is not None:
            try:
                redis_ok = await redis.ping()
            except Exception:
                redis_ok = False
        else:
            redis_ok = False

        mode = cache_mode()
        if mode == "redis":
            redis_status = "ok"
        elif mode == "memory":
            redis_status = "memory"
        else:
            redis_status = "unavailable"

        return success({
            "database": "ok" if db_ok else "error",
            "redis": redis_status,
            "status": "running"
        })
    except Exception as e:
        return {"code": 500, "message": str(e), "data": {"status": "degraded"}, "timestamp": 0}


@router.get("/sporttery/probe")
async def probe_sporttery(current_user: str = Depends(get_current_admin_user)):
    """Test sporttery.cn connectivity (WAF 567 / pool size / proxy config)."""
    from crawler.sporttery_client import probe_sporttery_fetch

    data = await probe_sporttery_fetch(force_refresh=True)
    msg = "体彩 API 正常" if data.get("ok") else (data.get("last_error") or "体彩 API 不可用")
    return success(data, msg)


@router.post("/crawler/run")
async def trigger_crawler(db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_admin_user)):
    logger.info("Manual crawler run triggered")
    result = await run_all_crawlers(db)
    return success(result, "爬虫任务已完成")


@router.post("/crawler/run/{crawler_type}")
async def trigger_crawler_type(crawler_type: str, db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_admin_user)):
    crawlers = {
        "schedule": run_schedule_crawler,
        "team": run_team_crawler,
        "odds": run_all_odds_crawlers
    }
    if crawler_type not in crawlers:
        return {"code": 400, "message": f"Invalid crawler type: {crawler_type}"}

    result = await crawlers[crawler_type](db)
    return success(result, f"{crawler_type}爬虫已完成")


@router.post("/crawler/league/{slug}")
async def trigger_league_crawler(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    logger.info(f"Manual league crawler triggered: {slug}")
    result = await run_league_crawler(db, slug)
    return success(result, f"联赛爬虫已完成: {slug}")


@router.get("/crawler/status")
async def get_crawler_status(db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_admin_user)):
    logs = (await db.execute(
        select(CrawlerLog).order_by(CrawlerLog.start_time.desc()).limit(10)
    )).scalars().all()

    return success([
        {
            "id": log.id, "crawler_type": log.crawler_type,
            "status": log.status, "records_count": log.records_count,
            "error_message": log.error_message,
            "start_time": log.start_time.isoformat() if log.start_time else None,
            "end_time": log.end_time.isoformat() if log.end_time else None
        }
        for log in logs
    ])


@router.get("/config")
async def get_config(current_user: str = Depends(get_current_admin_user)):
    return success(get_runtime_config())


@router.put("/config")
async def update_config(config: ConfigRequest, current_user: str = Depends(get_current_admin_user)):
    data = {}
    if config.deepseek_api_key is not None:
        data["deepseek_api_key"] = config.deepseek_api_key
    if config.deepseek_api_url is not None:
        data["deepseek_api_url"] = config.deepseek_api_url
    if config.qwen_api_key is not None:
        data["qwen_api_key"] = config.qwen_api_key
    if config.qwen_api_url is not None:
        data["qwen_api_url"] = config.qwen_api_url
    if config.glm_api_key is not None:
        data["glm_api_key"] = config.glm_api_key
    if config.glm_api_url is not None:
        data["glm_api_url"] = config.glm_api_url
    if config.fallback_api_key is not None:
        data["fallback_api_key"] = config.fallback_api_key
    if config.odds_api_key is not None:
        data["odds_api_key"] = config.odds_api_key
    if config.football_data_api_key is not None:
        data["football_data_api_key"] = config.football_data_api_key

    if not data:
        return {"code": 400, "message": "请至少提供一项配置"}

    save_runtime_config(data)

    # Clear prediction cache when API keys change so new models take effect immediately
    if any(k.endswith("api_key") for k in data):
        try:
            from db.redis_client import get_redis
            redis = await get_redis()
            if redis is not None:
                keys = await redis.keys("prediction:*")
                if keys:
                    await redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} prediction cache entries due to config change")
        except Exception as e:
            logger.warning(f"Failed to clear prediction cache: {e}")

    return success(get_runtime_config(), "配置已保存，即时生效")


class ConfigTestRequest(BaseModel):
    model: str = "deepseek"  # deepseek / qwen / glm


MODEL_CONFIG = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "env_url": "DEEPSEEK_API_URL",
        "default_url": "https://api.deepseek.com/v1/chat/completions",
        "api_model": "deepseek-chat",
        "label": "DeepSeek"
    },
    "qwen": {
        "env_key": "QWEN_API_KEY",
        "env_url": "QWEN_API_URL",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "api_model": "qwen-plus",
        "label": "通义千问"
    },
    "glm": {
        "env_key": "GLM_API_KEY",
        "env_url": "GLM_API_URL",
        "default_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_model": "glm-4-flash",
        "label": "智谱GLM"
    }
}


@router.post("/config/test")
async def test_api_connection(config: ConfigTestRequest = None, current_user: str = Depends(get_current_admin_user)):
    """Test LLM API connectivity"""
    import os
    import httpx

    if config is None:
        config = ConfigTestRequest()

    mc = MODEL_CONFIG.get(config.model)
    if not mc:
        return {"code": 400, "message": f"未知模型: {config.model}", "data": {"ok": False}}

    api_key = os.getenv(mc["env_key"], "")
    api_url = os.getenv(mc["env_url"], "") or mc["default_url"]

    if not api_key:
        return {"code": 400, "message": f"{mc['label']} API Key 未配置", "data": {"ok": False, "model": mc['label']}}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": mc["api_model"],
                    "messages": [{"role": "user", "content": "回复OK"}],
                    "max_tokens": 5
                }
            )
            status = resp.status_code
            if status == 200:
                elapsed = resp.elapsed.total_seconds()
                return success({
                    "ok": True,
                    "model": mc["label"],
                    "status_code": status,
                    "latency_seconds": round(elapsed, 2),
                    "message": f"{mc['label']} API 连接成功"
                }, "连接成功")
            else:
                body = resp.text[:300]
                return {"code": status, "message": f"API 返回 {status}", "data": {
                    "ok": False, "model": mc["label"], "status_code": status,
                    "response": body
                }}

    except httpx.TimeoutException:
        return {"code": 504, "message": f"{mc['label']} API 连接超时", "data": {"ok": False, "model": mc["label"]}}
    except Exception as e:
        return {"code": 500, "message": f"连接失败: {str(e)}", "data": {"ok": False, "model": mc["label"]}}


@router.post("/config/test-odds")
async def test_odds_api_connection(current_user: str = Depends(get_current_admin_user)):
    """Test The Odds API connectivity and World Cup odds availability."""
    import os
    import time

    from crawler.the_odds_api_client import fetch_world_cup_odds, find_odds_api_match
    from db import async_session
    from db.models import Match
    from sqlalchemy import select

    api_key = os.getenv("ODDS_API_KEY", "")
    if not api_key:
        return {
            "code": 400,
            "message": "The Odds API Key 未配置",
            "data": {"ok": False, "model": "The Odds API"},
        }

    start = time.monotonic()
    pool = await fetch_world_cup_odds()
    elapsed = round(time.monotonic() - start, 2)

    if not pool:
        return {
            "code": 502,
            "message": "API 已连接但未返回世界杯赛事盘口（可能尚未开盘或 Key 额度不足）",
            "data": {
                "ok": False,
                "model": "The Odds API",
                "latency_seconds": elapsed,
                "events_count": 0,
            },
        }

    db_matched = 0
    sample_db_match = None
    try:
        async with async_session() as db:
            matches = (await db.execute(
                select(Match).where(Match.status.in_(match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)))
            )).scalars().all()
            for m in matches:
                if find_odds_api_match(m.team_a, m.team_b, m.match_time, pool):
                    db_matched += 1
                    if not sample_db_match:
                        sample_db_match = f"{m.team_a} vs {m.team_b}"
    except Exception as e:
        logger.warning(f"Odds API test DB match check failed: {e}")

    ev = pool[0]
    h2h = ev.get("h2h") or {}
    return success({
        "ok": True,
        "model": "The Odds API",
        "latency_seconds": elapsed,
        "events_count": len(pool),
        "db_matched": db_matched,
        "sample_api_match": f"{ev.get('home_team_cn')} vs {ev.get('away_team_cn')}",
        "sample_db_match": sample_db_match,
        "sample_odds": {
            "home_win": h2h.get("home_win"),
            "draw": h2h.get("draw"),
            "away_win": h2h.get("away_win"),
        },
        "message": f"The Odds API 连接成功，{len(pool)} 场 API 赛事，{db_matched} 场可匹配本地赛程",
    }, "连接成功")


@router.post("/config/test-football-data")
async def test_football_data_connection(current_user: str = Depends(get_current_admin_user)):
    """Test football-data.org connectivity and Premier League data."""
    import time

    from crawler.football_data_client import fetch_standings, fetch_competition_matches, _api_key

    if not _api_key():
        return {
            "code": 400,
            "message": "Football-Data API Key 未配置",
            "data": {"ok": False, "model": "football-data.org"},
        }

    start = time.monotonic()
    standings = await fetch_standings("PL", 2025)
    matches = await fetch_competition_matches("PL", 2025)
    elapsed = round(time.monotonic() - start, 2)

    if not standings and not matches:
        return {
            "code": 502,
            "message": "API 已连接但未返回英超数据（请检查 Key 或额度）",
            "data": {
                "ok": False,
                "model": "football-data.org",
                "latency_seconds": elapsed,
                "teams_count": 0,
                "matches_count": 0,
            },
        }

    sample_team = standings[0]["name_en"] if standings else None
    return success({
        "ok": True,
        "model": "football-data.org",
        "latency_seconds": elapsed,
        "teams_count": len(standings),
        "matches_count": len(matches),
        "sample_team": sample_team,
        "message": f"football-data.org 连接成功，英超 {len(standings)} 队 / {len(matches)} 场",
    }, "连接成功")


# ── Invite Code Management ─────────────────────────────────────

@router.post("/invite-codes/generate")
async def generate_invite_code(
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    import random
    import string

    # Generate unique 6-digit numeric code
    code = None
    for _ in range(20):
        candidate = ''.join(random.choices(string.digits, k=6))
        existing = (await db.execute(
            select(InviteCode).where(InviteCode.code == candidate)
        )).scalar_one_or_none()
        if not existing:
            code = candidate
            break
    if not code:
        return error(500, "邀请码生成失败，请重试")

    now = utc_now()
    expires_at = now + timedelta(days=3)
    invite = InviteCode(code=code, expires_at=expires_at, created_at=now)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    logger.info(f"Generated invite code: {code}, expires: {expires_at}")
    return success({
        "id": invite.id,
        "code": invite.code,
        "expires_at": format_utc_iso(invite.expires_at),
        "use_count": 0,
        "created_at": format_utc_iso(invite.created_at),
    }, f"邀请码 {code} 已生成，有效期 3 天，可多人使用")


@router.get("/invite-codes")
async def list_invite_codes(
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    result = await db.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc()).limit(50)
    )
    codes = result.scalars().all()
    now = utc_now()
    return success([{
        "id": c.id,
        "code": c.code,
        "use_count": c.use_count,
        "is_active": c.expires_at > now,
        "created_at": format_utc_iso(c.created_at),
        "expires_at": format_utc_iso(c.expires_at),
    } for c in codes])


@router.delete("/invite-codes/{code_id}")
async def delete_invite_code(
    code_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    result = await db.execute(select(InviteCode).where(InviteCode.id == code_id))
    code = result.scalar_one_or_none()
    if not code:
        return error(404, "邀请码不存在")
    await db.delete(code)
    await db.commit()
    return success(None, "邀请码已删除")


@router.post("/predictions/batch")
async def trigger_batch_predict(
    model: str = Query("auto"),
    competition: str = Query("worldcup-2026", description="仅预测该赛事；传 all 表示全部未开始比赛"),
    background: bool = Query(True, description="后台执行，避免 HTTP 超时"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    from service.batch_predict_job import get_batch_state, start_batch_predict_job

    actual_model = None if model == "auto" else model
    comp_slug = None if competition == "all" else competition
    if comp_slug and not is_valid_competition(comp_slug):
        return error(400, f"未知赛事: {competition}")

    if background:
        state = await start_batch_predict_job(actual_model, comp_slug)
        if not state.get("started"):
            reason = state.get("reason") or "already_running"
            msg = "批量预测正在进行中" if reason == "already_running" else "已有后台任务在运行"
            return error(409, msg, data=state)
        return success(state, "批量预测已在后台启动")

    service = PredictionService()
    results = await service.batch_predict(db, actual_model, competition_slug=comp_slug)
    return success({"count": len(results)}, f"批量预测完成，共处理{len(results)}场")


@router.get("/predictions/batch/status")
async def batch_predict_status(current_user: str = Depends(get_current_admin_user)):
    from service.batch_predict_job import get_batch_state
    return success(get_batch_state())


@router.get("/calibration/params")
async def get_calibration_params(current_user: str = Depends(get_current_admin_user)):
    """Return current calibrated model parameters."""
    return success(load_calibrated_params())


@router.get("/calibration/backtest")
async def get_backtest_results(current_user: str = Depends(get_current_admin_user)):
    """Run backtest on 2014/2018/2022 historical matches."""
    params = load_calibrated_params()
    result = run_backtest(params)
    return success({
        "metrics": {k: v for k, v in result.items() if k != "details"},
        "sample_details": result["details"][:10],
        "params_version": params.get("calibrated_at"),
    })


@router.post("/calibration/run")
async def run_calibration(
    iterations: int = Query(80, ge=20, le=200),
    current_user: str = Depends(get_current_admin_user),
):
    """Auto-calibrate model parameters using historical World Cup data."""
    logger.info(f"Starting calibration with {iterations} iterations")
    params = calibrate(iterations=iterations)

    try:
        from db.redis_client import get_redis
        redis = await get_redis()
        if redis is not None:
            keys = await redis.keys("prediction:*")
            if keys:
                await redis.delete(*keys)
    except Exception:
        pass

    bt = params.get("backtest", {})
    return success({
        "calibrated_at": params.get("calibrated_at"),
        "result_accuracy": bt.get("result_accuracy"),
        "score_top3_accuracy": bt.get("score_top3_accuracy"),
        "brier_score": bt.get("brier_score"),
        "upset_detection_rate": bt.get("upset_detection_rate"),
        "collusion_detection_rate": bt.get("collusion_detection_rate"),
    }, "参数校准完成，预测缓存已清除")


# ── User Management ─────────────────────────────────────────────

@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    total_count = len(users)
    active_count = sum(1 for u in users if u.is_active)

    return success({
        "total": total_count,
        "active": active_count,
        "competition_options": [{
            "slug": c["slug"],
            "short_name": c["short_name"],
            "name_key": c["name_key"],
        } for c in list_competitions()],
        "users": [{
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "updated_at": u.updated_at.isoformat() if u.updated_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "access_expires_at": u.access_expires_at.isoformat() if u.access_expires_at else None,
            "allowed_competitions": parse_allowed_competitions(u.allowed_competitions),
            "has_all_competitions": parse_allowed_competitions(u.allowed_competitions) is None,
            "can_access_sporttery": bool(u.can_access_sporttery),
        } for u in users]
    })


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    if len(req.new_password) < 6:
        return error(400, "密码长度不能少于 6 个字符")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error(404, "用户不存在")

    user.hashed_password = pwd_context.hash(req.new_password)
    await db.commit()

    logger.info(f"Admin {current_user} reset password for user: {user.username}")
    return success(None, f"用户 {user.username} 的密码已重置")


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error(404, "用户不存在")
    if user.username == current_user:
        return error(400, "不能禁用自己的账号")

    user.is_active = not user.is_active
    await db.commit()

    status = "启用" if user.is_active else "禁用"
    logger.info(f"Admin {current_user} {status} user: {user.username}")
    return success({"is_active": user.is_active}, f"用户 {user.username} 已{status}")


class UpdateUserAccessRequest(BaseModel):
    access_expires_at: Optional[datetime] = None
    clear_access_expires_at: bool = False
    allowed_competitions: Optional[list[str]] = None
    grant_all_competitions: bool = False
    can_access_sporttery: Optional[bool] = None


@router.patch("/users/{user_id}/access")
async def update_user_access(
    user_id: int,
    req: UpdateUserAccessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error(404, "用户不存在")

    if req.clear_access_expires_at:
        user.access_expires_at = None
    elif req.access_expires_at is not None:
        user.access_expires_at = req.access_expires_at

    if req.grant_all_competitions:
        user.allowed_competitions = None
    elif req.allowed_competitions is not None:
        invalid = [s for s in req.allowed_competitions if not is_valid_competition(s)]
        if invalid:
            return error(400, f"未知赛事: {', '.join(invalid)}")
        user.allowed_competitions = serialize_allowed_competitions(req.allowed_competitions)

    if req.can_access_sporttery is not None:
        user.can_access_sporttery = req.can_access_sporttery

    await db.commit()
    await db.refresh(user)

    allowed = parse_allowed_competitions(user.allowed_competitions)
    logger.info(f"Admin {current_user} updated access for user: {user.username}")
    return success({
        "access_expires_at": user.access_expires_at.isoformat() if user.access_expires_at else None,
        "allowed_competitions": allowed,
        "has_all_competitions": allowed is None,
        "can_access_sporttery": bool(user.is_admin or user.can_access_sporttery),
    }, f"用户 {user.username} 的访问权限已更新")


@router.get("/runtime-logs")
async def get_runtime_logs(
    source: str = Query("backend", description="backend | frontend"),
    lines: int = Query(300, ge=1, le=2000),
    current_user: str = Depends(get_current_admin_user),
):
    """Tail backend.log or frontend.log from project root (admin only)."""
    key = source.lower().strip()
    if key not in LOG_SOURCES:
        return error(400, f"Invalid source: {source}. Use: {', '.join(LOG_SOURCES)}")
    data = tail_log_file(key, lines)
    return success(data)
