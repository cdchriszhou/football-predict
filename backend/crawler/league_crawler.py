"""
League data crawler — schedule, teams, and odds for五大联赛 via The Odds API.

Uses the same prediction pipeline as World Cup once data is in DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from data.competitions import get_competition, COMPETITIONS
from data.league_seed import ensure_league_data
from data.match_status import season_label_for
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values
from crawler.club_data_sync import sync_league_from_football_data
from crawler.football_data_client import _api_key as fd_api_configured
from db.models import Match, Team, Odds
from .base_crawler import _log_crawler, _safe_crawler_fail, crawler_lock
from .the_odds_api_client import fetch_sport_odds, find_odds_api_match
from .odds_crawler import _build_meta, _compose_source
from .sporttery_client import fetch_sporttery_on_sale, find_sporttery_match, sporttery_row_has_sale_data, to_db_odds
from utils.logger import logger

import json


def _display_name(ev: dict, side: str) -> str:
    """Prefer Chinese mapping when available, else English API name."""
    if side == "home":
        cn = ev.get("home_team_cn")
        en = ev.get("home_team_en")
    else:
        cn = ev.get("away_team_cn")
        en = ev.get("away_team_en")
    if cn and cn != en:
        return cn
    return en or cn or ""


def _team_strength_from_rank(rank: int, total: int) -> dict:
    """Derive ability scores from league table position (1=best)."""
    pct = max(0, 1 - (rank - 1) / max(total - 1, 1))
    base = 62 + pct * 28
    return {
        "attack": round(base + pct * 6),
        "defend": round(base - (1 - pct) * 4),
        "midfield": round(base),
        "speed": round(base - 2),
        "physical": round(base - 1),
    }


async def _sync_league_teams(db: AsyncSession, slug: str, events: list[dict]) -> int:
    """Build/update club teams from odds API fixtures."""
    comp = get_competition(slug)
    if not comp:
        return 0

    strength: dict[str, list[float]] = {}
    for ev in events:
        h2h = ev.get("h2h") or {}
        home = _display_name(ev, "home")
        away = _display_name(ev, "away")
        if not home or not away:
            continue
        hw, aw = h2h.get("home_win", 2), h2h.get("away_win", 2)
        strength.setdefault(home, []).append(1 / hw if hw else 0.5)
        strength.setdefault(away, []).append(1 / aw if aw else 0.5)

    ranked = sorted(strength.keys(), key=lambda t: mean(strength[t]), reverse=True)
    total = len(ranked) or 20
    count = 0

    for i, name in enumerate(ranked, start=1):
        en_name = name
        for ev in events:
            if _display_name(ev, "home") == name:
                en_name = ev.get("home_team_en") or name
                break
            if _display_name(ev, "away") == name:
                en_name = ev.get("away_team_en") or name
                break

        abilities = _team_strength_from_rank(i, total)
        existing = (await db.execute(
            select(Team).where(Team.name == name, Team.competition_slug == slug)
        )).scalar_one_or_none()

        if existing:
            existing.rank = i
            existing.name_en = en_name
            for k, v in abilities.items():
                setattr(existing, k, v)
            existing.tactic = existing.tactic or "联赛常规"
            existing.price = existing.price or "-"
        else:
            db.add(Team(
                competition_slug=slug,
                name=name,
                name_en=en_name,
                flag_url="",
                rank=i,
                tactic="联赛常规",
                price="-",
                group_name=None,
                **abilities,
            ))
            count += 1

    await db.flush()
    return count


async def _sync_league_schedule(db: AsyncSession, slug: str, events: list[dict]) -> dict:
    comp = get_competition(slug)
    if not comp:
        return {"created": 0, "updated": 0}

    existing = (await db.execute(
        select(Match).where(Match.competition_slug == slug)
    )).scalars().all()
    existing_map = {
        (m.team_a, m.team_b, m.match_time.date() if m.match_time else None): m
        for m in existing
    }

    created = updated = 0
    season = season_label_for(comp)
    for ev in events:
        home = _display_name(ev, "home")
        away = _display_name(ev, "away")
        kickoff = ev.get("kickoff")
        if not home or not away or not kickoff:
            continue
        if kickoff.tzinfo:
            kickoff = kickoff.astimezone(timezone.utc).replace(tzinfo=None)

        key = (home, away, kickoff.date())
        current = existing_map.get(key)
        if current:
            if current.status == MATCH_UPCOMING:
                current.match_time = kickoff
                if season and not current.season:
                    current.season = season
                updated += 1
            continue

        db.add(Match(
            competition_slug=slug,
            stage="联赛",
            group_name=None,
            team_a=home,
            team_b=away,
            match_time=kickoff,
            location=comp.get("short_name", slug),
            stadium="",
            status=MATCH_UPCOMING,
            season=season,
        ))
        created += 1

    await db.flush()
    return {"created": created, "updated": updated}


async def _sync_league_odds(db: AsyncSession, slug: str, events: list[dict]) -> dict:
    active = match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)
    matches = (await db.execute(
        select(Match).where(
            Match.competition_slug == slug,
            Match.status.in_(active),
        )
    )).scalars().all()

    sporttery_pool = await fetch_sporttery_on_sale()
    hints = tuple(get_competition(slug).get("sporttery_league_hints") or ())

    created = updated = skipped = 0
    for match in matches:
        api_odds = find_odds_api_match(match.team_a, match.team_b, match.match_time, events)
        st_raw = find_sporttery_match(
            match.team_a, match.team_b, match.match_time, sporttery_pool,
            league_hints=hints,
        )
        st_odds = to_db_odds(st_raw, match.team_a, match.team_b) if st_raw else None

        european = (api_odds or {}).get("european")
        macau = (api_odds or {}).get("macau")
        has_sporttery = sporttery_row_has_sale_data(st_odds)
        has_market = bool(european and european.get("win_win"))

        if not has_sporttery and not has_market:
            skipped += 1
            continue

        if has_sporttery:
            win_win, draw, win_lose = st_odds["win_win"], st_odds["draw"], st_odds["win_lose"]
            handicap = st_odds.get("handicap")
            handicap_win = st_odds.get("handicap_win")
            handicap_draw = st_odds.get("handicap_draw")
            handicap_lose = st_odds.get("handicap_lose")
            over_under = st_odds.get("over_under")
            over_odds = st_odds.get("over_odds")
            under_odds = st_odds.get("under_odds")
            sporttery_meta = {"match_id": st_odds.get("sporttery_match_id"), "league": st_raw.get("league") if st_raw else None}
        else:
            win_win = european["win_win"]
            draw = european["draw"]
            win_lose = european["win_lose"]
            handicap = macau.get("handicap") if macau else None
            handicap_win = macau.get("handicap_win") if macau else None
            handicap_draw = macau.get("handicap_draw") if macau else None
            handicap_lose = macau.get("handicap_lose") if macau else None
            over_under = european.get("over_under")
            over_odds = european.get("over_odds")
            under_odds = european.get("under_odds")
            sporttery_meta = None

        score_odds_raw = {}
        meta = _build_meta(european, macau, sporttery_meta)
        score_odds_raw["_meta"] = meta
        source = _compose_source(european, has_sporttery)

        existing = (await db.execute(select(Odds).where(Odds.match_id == match.id))).scalar_one_or_none()
        payload = {
            "win_win": win_win, "draw": draw, "win_lose": win_lose,
            "handicap": handicap,
            "handicap_win": handicap_win, "handicap_draw": handicap_draw, "handicap_lose": handicap_lose,
            "over_under": over_under, "over_odds": over_odds, "under_odds": under_odds,
            "score_odds": json.dumps(score_odds_raw, ensure_ascii=False),
            "source": source,
            "update_time": datetime.now(),
        }
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Odds(match_id=match.id, **payload))
            created += 1

    await db.flush()
    return {"created": created, "updated": updated, "skipped": skipped}


async def run_league_crawler(db: AsyncSession, slug: str) -> dict:
    """Sync schedule, teams, squads, and odds for one league competition."""
    comp = get_competition(slug)
    if not comp or comp["type"] != "club":
        return {"status": "skipped", "message": f"Not a club league: {slug}"}

    async with crawler_lock:
        start = datetime.now()
        try:
            fd_result = {"status": "skipped"}
            if fd_api_configured():
                fd_result = await sync_league_from_football_data(db, slug)
                if fd_result.get("status") != "success":
                    seed = await ensure_league_data(db, slug)
                    fd_result = {**fd_result, "status": "seeded", "seed": seed}
            else:
                seed = await ensure_league_data(db, slug)
                fd_result = {"status": "seeded", "seed": seed}

            events = await fetch_sport_odds(comp["odds_api_sport_key"], comp["short_name"])
            odds = await _sync_league_odds(db, slug, events or [])

            sched = {"created": 0, "updated": 0}
            teams = 0
            if fd_result.get("status") != "success" and events:
                sched = await _sync_league_schedule(db, slug, events)
                teams = await _sync_league_teams(db, slug, events)

            total = (
                (fd_result.get("schedule") or {}).get("created", 0)
                + (fd_result.get("schedule") or {}).get("updated", 0)
                + fd_result.get("teams", 0)
                + (fd_result.get("squads") or {}).get("players", 0)
                + sched.get("created", 0) + sched.get("updated", 0)
                + teams
                + odds.get("created", 0) + odds.get("updated", 0)
            )

            await _log_crawler(db, f"league:{slug}", "success", total, start=start)
            logger.info(f"League crawler [{slug}]: fd={fd_result}, odds={odds}")
            return {
                "status": "success" if fd_result.get("status") in ("success", "seeded") else fd_result.get("status", "success"),
                "slug": slug,
                "records": total,
                "football_data": fd_result,
                "schedule": fd_result.get("schedule") or sched,
                "teams_new": teams,
                "odds": odds,
            }
        except Exception as e:
            await _safe_crawler_fail(db, f"league:{slug}", str(e), start)
            raise


async def run_all_league_crawlers(db: AsyncSession) -> dict:
    results = {}
    for slug, comp in COMPETITIONS.items():
        if comp["type"] == "club":
            try:
                results[slug] = await run_league_crawler(db, slug)
            except Exception as e:
                results[slug] = {"status": "failed", "error": str(e)}
    return results
