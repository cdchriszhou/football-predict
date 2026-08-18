from sqlalchemy.ext.asyncio import AsyncSession
from .odds_crawler import run_odds_crawler, run_all_odds_crawlers
from .league_crawler import run_all_league_crawlers, run_league_crawler
from utils.logger import logger


async def run_all_crawlers(db: AsyncSession) -> dict:
    from service.write_guard import is_heavy_job_running

    if is_heavy_job_running():
        logger.info("Crawler run skipped (heavy job in progress)")
        return {"status": "skipped", "reason": "heavy_job_running"}

    results = {}

    logger.info("Starting league crawlers...")
    results["leagues"] = await run_all_league_crawlers(db)

    logger.info("Starting odds crawler...")
    results["odds"] = await run_all_odds_crawlers(db)

    logger.info(f"Crawler run complete: {results}")
    return results
