from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from crawler import run_all_crawlers
from crawler.odds_crawler import run_all_odds_crawlers
from data.competitions import list_competitions
from data.match_status import maintain_competition_matches
from service.prediction_service import PredictionService
from db import async_session
from db.sqlite_write import IS_SQLITE, commit_session, write_lock, _commit_with_retry
from utils.logger import logger

scheduler = AsyncIOScheduler()


async def _crawl_all():
    from service.write_guard import is_heavy_job_running
    if is_heavy_job_running():
        logger.info("Scheduled crawl skipped (heavy job in progress)")
        return
    async with async_session() as db:
        try:
            if IS_SQLITE:
                async with write_lock:
                    await run_all_crawlers(db)
                    await _commit_with_retry(db)
            else:
                await run_all_crawlers(db)
                await commit_session(db)
        except Exception as e:
            await db.rollback()
            logger.error(f"Scheduled crawl failed: {e}")


async def _crawl_odds():
    from service.write_guard import is_heavy_job_running
    if is_heavy_job_running():
        logger.info("Scheduled odds crawl skipped (manual refresh in progress)")
        return
    async with async_session() as db:
        try:
            if IS_SQLITE:
                async with write_lock:
                    await run_all_odds_crawlers(db)
                    await _commit_with_retry(db)
            else:
                await run_all_odds_crawlers(db)
                await commit_session(db)
        except Exception as e:
            await db.rollback()
            logger.error(f"Scheduled odds crawl failed: {e}")


async def _sync_live_scores():
    from service.write_guard import is_heavy_job_running
    if is_heavy_job_running():
        return
    async with async_session() as db:
        try:
            from data.match_status import sync_live_scores
            from service.score_backtest import invalidate_daily_report_cache
            if IS_SQLITE:
                async with write_lock:
                    result = await sync_live_scores(db, "worldcup-2026", network=True)
                    if int(result.get("updated") or 0):
                        logger.info(f"Scheduled live score sync: {result}")
                        await invalidate_daily_report_cache("worldcup-2026")
                    await _commit_with_retry(db)
            else:
                result = await sync_live_scores(db, "worldcup-2026", network=True)
                if int(result.get("updated") or 0):
                    logger.info(f"Scheduled live score sync: {result}")
                    await invalidate_daily_report_cache("worldcup-2026")
                await commit_session(db)
        except Exception as e:
            await db.rollback()
            logger.error(f"Scheduled live score sync failed: {e}")


async def _maintain_matches():
    from service.write_guard import is_heavy_job_running
    if is_heavy_job_running():
        logger.info("Scheduled match maintenance skipped (manual refresh in progress)")
        return
    async with async_session() as db:
        try:
            if IS_SQLITE:
                async with write_lock:
                    for comp in list_competitions():
                        if comp.get("type") == "racing":
                            continue
                        try:
                            await maintain_competition_matches(db, comp["slug"])
                        except Exception as e:
                            logger.warning(f"Scheduled maintain failed [{comp['slug']}]: {e}")
                            await db.rollback()
                    await _commit_with_retry(db)
            else:
                for comp in list_competitions():
                    if comp.get("type") == "racing":
                        continue
                    try:
                        await maintain_competition_matches(db, comp["slug"])
                    except Exception as e:
                        logger.warning(f"Scheduled maintain failed [{comp['slug']}]: {e}")
                        await db.rollback()
                await commit_session(db)
        except Exception as e:
            await db.rollback()
            logger.error(f"Scheduled match maintenance failed: {e}")


async def _batch_predict():
    from service.write_guard import is_heavy_job_running
    if is_heavy_job_running():
        logger.info("Scheduled batch predict skipped (manual refresh in progress)")
        return
    async with async_session() as db:
        try:
            service = PredictionService()
            await service.batch_predict(db)
            await db.rollback()
        except Exception as e:
            await db.rollback()
            logger.error(f"Scheduled batch predict failed: {e}")


def start_scheduler():
    scheduler.add_job(
        _crawl_all,
        CronTrigger(hour="*/6"),
        id="crawl_all",
        replace_existing=True,
        name="全量数据爬取（每6小时）"
    )

    scheduler.add_job(
        _maintain_matches,
        CronTrigger(minute="5"),
        id="maintain_matches",
        replace_existing=True,
        name="赛程状态维护（每小时）"
    )

    scheduler.add_job(
        _crawl_odds,
        CronTrigger(minute="0"),
        id="crawl_odds_hourly",
        replace_existing=True,
        name="盘口数据更新（每小时）"
    )

    scheduler.add_job(
        _batch_predict,
        CronTrigger(hour="8,18"),
        id="batch_predict",
        replace_existing=True,
        name="批量预测（每天8:00/18:00）"
    )

    scheduler.add_job(
        _sync_live_scores,
        IntervalTrigger(minutes=1),
        id="sync_live_scores",
        replace_existing=True,
        name="世界杯滚球比分（每分钟）",
    )

    scheduler.start()
    logger.info("Scheduler started with 5 jobs")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
