"""
Odds crawler — real betting odds only (no derived/simulated fallbacks).

Data sources (priority):
  1. sporttery.cn — official China Sports Lottery (when on sale)
  2. The Odds API — European 1X2 + Asian handicap + totals (requires ODDS_API_KEY)

Matches without any real source are skipped (existing derived rows may be removed).
"""
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from db.models import Match, Odds
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values
from .base_crawler import _log_crawler, _safe_crawler_fail, crawler_lock
from .sporttery_client import (
    fetch_sporttery_on_sale,
    find_sporttery_match,
    sporttery_row_has_sale_data,
    to_db_odds,
)
from .the_odds_api_client import fetch_world_cup_odds, find_odds_api_match
from data.competitions import COMPETITIONS, get_competition, league_hints_for
from utils.logger import logger


def _build_meta(
    european: dict | None,
    macau: dict | None,
    sporttery_meta: dict | None = None,
) -> dict:
    sources = []
    if european and european.get("win_win"):
        sources.append(european.get("source", "the-odds-api"))
    if macau and macau.get("win_win"):
        sources.append(macau.get("source", "the-odds-api:asian_handicap"))
    if sporttery_meta:
        sources.append("sporttery.cn")
    meta = {"sources": sources}
    if european:
        meta["european"] = european
    if macau:
        meta["macau"] = macau
    if sporttery_meta:
        meta["sporttery"] = sporttery_meta
    return meta


def _compose_source(european: dict | None, sporttery: bool) -> str:
    parts = []
    if sporttery:
        parts.append("sporttery.cn")
    if european and european.get("win_win"):
        parts.append("the-odds-api")
    return "+".join(parts) if parts else "none"


def _parse_closing_date(comp: dict) -> datetime | None:
    raw = comp.get("closing_date")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _competition_supports_odds(comp: dict) -> bool:
    if comp.get("type") == "racing":
        return False
    if comp.get("odds_api_sport_key"):
        return True
    return bool((comp.get("features") or {}).get("sporttery"))


def _season_ended(comp: dict, now: datetime | None = None) -> bool:
    closing = _parse_closing_date(comp)
    if not closing:
        return False
    now = now or datetime.utcnow()
    return now > closing


def _odds_crawler_slugs() -> list[str]:
    slugs = []
    now = datetime.utcnow()
    for slug, comp in COMPETITIONS.items():
        if not _competition_supports_odds(comp):
            continue
        if comp.get("type") == "club" and _season_ended(comp, now):
            continue
        slugs.append(slug)
    return slugs


async def run_odds_crawler(
    db: AsyncSession,
    competition_slug: str = "worldcup-2026",
    *,
    sporttery_pool: list[dict] | None = None,
):
    """Update odds from real APIs only."""
    async with crawler_lock:
        start_time = datetime.now()
        try:
            matches = (await db.execute(
                select(Match)
                .where(
                    Match.competition_slug == competition_slug,
                    Match.status.in_(match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)),
                )
                .order_by(Match.match_time.asc())
            )).scalars().all()

            if sporttery_pool is None:
                sporttery_pool = await fetch_sporttery_on_sale()
            hints = league_hints_for(competition_slug) or ("世界", "世界杯", "World Cup", "FIFA")
            comp = get_competition(competition_slug)
            if competition_slug == "worldcup-2026":
                odds_api_pool = await fetch_world_cup_odds()
            elif comp and comp.get("odds_api_sport_key"):
                from .the_odds_api_client import fetch_sport_odds
                odds_api_pool = await fetch_sport_odds(
                    comp["odds_api_sport_key"], comp["short_name"]
                )
            else:
                odds_api_pool = []

            created = updated = skipped = removed = 0
            sporttery_matched = odds_api_matched = 0

            for match in matches:
                team_a, team_b = match.team_a, match.team_b

                st_raw = find_sporttery_match(
                    team_a, team_b, match.match_time, sporttery_pool,
                    league_hints=hints,
                )
                st_odds = to_db_odds(st_raw, team_a, team_b) if st_raw else None
                api_odds = find_odds_api_match(team_a, team_b, match.match_time, odds_api_pool)

                european = (api_odds or {}).get("european")
                macau = (api_odds or {}).get("macau")
                if api_odds:
                    odds_api_matched += 1

                has_sporttery = sporttery_row_has_sale_data(st_odds)
                has_market = bool(european and european.get("win_win"))

                if not has_sporttery and not has_market:
                    existing = (await db.execute(
                        select(Odds).where(Odds.match_id == match.id)
                    )).scalar_one_or_none()
                    if existing:
                        await db.execute(delete(Odds).where(Odds.match_id == match.id))
                        removed += 1
                    skipped += 1
                    continue

                if has_sporttery:
                    sporttery_matched += 1

                # 竞彩主字段：仅体彩官方；外围盘在 _meta
                if has_sporttery:
                    win_win = st_odds["win_win"]
                    draw = st_odds["draw"]
                    win_lose = st_odds["win_lose"]
                    handicap = st_odds.get("handicap")
                    handicap_win = st_odds.get("handicap_win")
                    handicap_draw = st_odds.get("handicap_draw")
                    handicap_lose = st_odds.get("handicap_lose")
                    over_under = st_odds.get("over_under")
                    over_odds = st_odds.get("over_odds")
                    under_odds = st_odds.get("under_odds")
                    score_odds_raw = dict(st_odds.get("score_odds") or {})
                    half_full_raw = dict(st_odds.get("half_full_odds") or {})
                    sporttery_meta = {
                        "match_id": st_odds.get("sporttery_match_id"),
                        "match_num": st_odds.get("sporttery_match_num"),
                        "league": st_raw.get("league") if st_raw else None,
                    }
                    odds_update_time = st_odds.get("update_time") or datetime.now()
                else:
                    win_win = draw = win_lose = None
                    handicap = handicap_win = handicap_draw = handicap_lose = None
                    over_under = over_odds = under_odds = None
                    score_odds_raw = {}
                    half_full_raw = {}
                    sporttery_meta = None
                    odds_update_time = datetime.now()

                if has_market and not has_sporttery:
                    win_win = european["win_win"]
                    draw = european["draw"]
                    win_lose = european["win_lose"]
                    over_under = european.get("over_under")
                    over_odds = european.get("over_odds")
                    under_odds = european.get("under_odds")
                    if macau:
                        handicap = macau.get("handicap")
                        handicap_win = macau.get("handicap_win")
                        handicap_draw = macau.get("handicap_draw")
                        handicap_lose = macau.get("handicap_lose")

                meta = _build_meta(european, macau, sporttery_meta)
                score_odds_raw["_meta"] = meta
                source = _compose_source(european, has_sporttery)

                existing = (await db.execute(
                    select(Odds).where(Odds.match_id == match.id)
                )).scalar_one_or_none()

                payload = dict(
                    win_win=win_win,
                    draw=draw,
                    win_lose=win_lose,
                    handicap=handicap,
                    handicap_win=handicap_win,
                    handicap_draw=handicap_draw,
                    handicap_lose=handicap_lose,
                    over_under=over_under,
                    over_odds=over_odds,
                    under_odds=under_odds,
                    score_odds=json.dumps(score_odds_raw, ensure_ascii=False),
                    half_full_odds=json.dumps(half_full_raw, ensure_ascii=False),
                    source=source,
                    update_time=odds_update_time,
                )

                if existing:
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(Odds(match_id=match.id, **payload))
                    created += 1

            await db.flush()

            log_source = f"sporttery({sporttery_matched})+odds-api({odds_api_matched})"
            await _log_crawler(db, "odds", "success", created + updated, start=start_time)
            logger.info(
                f"Odds (real only): +{created} ~{updated} -{removed} skip={skipped} "
                f"({log_source})"
            )
            return {
                "status": "success",
                "created": created,
                "updated": updated,
                "removed": removed,
                "skipped": skipped,
                "sporttery_matched": sporttery_matched,
                "odds_api_matched": odds_api_matched,
                "source": log_source,
            }

        except Exception as e:
            await _safe_crawler_fail(db, "odds", e, start_time)
            return {"status": "failed", "error": str(e)}


async def run_all_odds_crawlers(db: AsyncSession) -> dict:
    """Run odds crawler for eligible football competitions (one sporttery fetch)."""
    slugs = _odds_crawler_slugs()
    skipped = [s for s in COMPETITIONS if s not in slugs]
    if skipped:
        logger.info(f"Odds crawl skipped competitions: {', '.join(skipped)}")

    sporttery_pool = await fetch_sporttery_on_sale()
    results: dict = {}
    for slug in slugs:
        results[slug] = await run_odds_crawler(
            db, slug, sporttery_pool=sporttery_pool
        )
    return results
