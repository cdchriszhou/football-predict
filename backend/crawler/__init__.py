from sqlalchemy.ext.asyncio import AsyncSession
from .schedule_crawler import run_schedule_crawler
from .team_crawler import run_team_crawler
from .odds_crawler import run_odds_crawler, run_all_odds_crawlers
from .league_crawler import run_all_league_crawlers
from utils.logger import logger


async def run_all_crawlers(db: AsyncSession) -> dict:
    results = {}

    logger.info("Starting schedule crawler...")
    results["schedule"] = await run_schedule_crawler(db)

    logger.info("Starting team crawler...")
    results["team"] = await run_team_crawler(db)

    logger.info("Starting odds crawler...")
    results["odds"] = await run_all_odds_crawlers(db)

    logger.info("Starting league crawlers...")
    results["leagues"] = await run_all_league_crawlers(db)

    logger.info(f"Crawler run complete: {results}")
    return results
