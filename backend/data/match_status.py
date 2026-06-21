"""Reconcile stale match statuses and remove duplicate seed fixtures."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from utils.logger import logger

from data.competitions import get_competition
from data.competition_status import _parse_iso
from utils.datetime_helpers import china_now

# Schedule stores naive Beijing local kickoff; allow ~2h15 regulation + ET slack.
MATCH_FINISH_BUFFER = timedelta(hours=2, minutes=45)
from data.status_constants import (
    ACTIVE_MATCH_STATUSES,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_LEGACY_MAP,
    MATCH_UPCOMING,
    PLAYER_LEGACY_MAP,
    match_status_in_db_values,
    normalize_match_status,
)
from db.models import Match, Odds, Player, Prediction, Team

_ACTIVE = match_status_in_db_values(*ACTIVE_MATCH_STATUSES)


def season_label_for(comp: dict) -> str | None:
    year = comp.get("season_year")
    if year is None:
        return None
    y = int(year)
    return f"{y}/{str(y + 1)[-2:]}"


async def migrate_legacy_statuses(db: AsyncSession) -> dict:
    """One-time idempotent migration: Chinese status values → English codes."""
    legacy_match_statuses = tuple(MATCH_LEGACY_MAP.keys())
    legacy_player_statuses = tuple(PLAYER_LEGACY_MAP.keys())
    match_pending = (await db.execute(
        select(func.count(Match.id)).where(Match.status.in_(legacy_match_statuses))
    )).scalar() or 0
    player_pending = (await db.execute(
        select(func.count(Player.id)).where(Player.status.in_(legacy_player_statuses))
    )).scalar() or 0
    if not match_pending and not player_pending:
        return {"matches": 0, "players": 0}

    match_updated = player_updated = 0
    try:
        for legacy, canonical in MATCH_LEGACY_MAP.items():
            result = await db.execute(
                update(Match).where(Match.status == legacy).values(status=canonical)
            )
            match_updated += int(result.rowcount or 0)
        for legacy, canonical in PLAYER_LEGACY_MAP.items():
            result = await db.execute(
                update(Player).where(Player.status == legacy).values(status=canonical)
            )
            player_updated += int(result.rowcount or 0)
        if match_updated or player_updated:
            await db.flush()
    except OperationalError as exc:
        if "locked" in str(exc).lower():
            logger.warning(f"Legacy status migration skipped (SQLite locked): {exc}")
            await db.rollback()
            return {"matches": 0, "players": 0}
        raise
    return {"matches": match_updated, "players": player_updated}


async def backfill_match_seasons(db: AsyncSession, slug: str) -> int:
    """Set season on club matches that were created without it."""
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return 0
    season = season_label_for(comp)
    if not season:
        return 0
    result = await db.execute(
        update(Match)
        .where(
            Match.competition_slug == slug,
            Match.season.is_(None),
        )
        .values(season=season)
    )
    updated = int(result.rowcount or 0)
    if updated:
        await db.flush()
    return updated


async def backfill_team_seasons(db: AsyncSession, slug: str) -> int:
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return 0
    season = season_label_for(comp)
    if not season:
        return 0
    result = await db.execute(
        update(Team)
        .where(
            Team.competition_slug == slug,
            Team.season.is_(None),
        )
        .values(season=season)
    )
    updated = int(result.rowcount or 0)
    if updated:
        await db.flush()
    return updated


async def dedupe_duplicate_fixtures(db: AsyncSession, slug: str) -> int:
    """Remove duplicate match rows sharing the same stage/group/teams (schedule re-sync artifact)."""
    rows = (await db.execute(
        select(Match).where(Match.competition_slug == slug)
    )).scalars().all()
    groups: dict[tuple, list[Match]] = {}
    for m in rows:
        key = (m.stage, m.group_name or "", m.team_a, m.team_b)
        groups.setdefault(key, []).append(m)

    removed = 0
    for items in groups.values():
        if len(items) <= 1:
            continue
        items.sort(
            key=lambda m: (
                1 if m.status == MATCH_FINISHED and m.result_a is not None else 0,
                1 if m.status == MATCH_LIVE else 0,
                -(m.id or 0),
            ),
            reverse=True,
        )
        for dup in items[1:]:
            await db.execute(delete(Prediction).where(Prediction.match_id == dup.id))
            await db.execute(delete(Odds).where(Odds.match_id == dup.id))
            await db.delete(dup)
            removed += 1
    if removed:
        await db.flush()
        logger.info("Deduped %d duplicate fixtures for %s", removed, slug)
    return removed


async def cleanup_orphan_seed_matches(db: AsyncSession, slug: str) -> int:
    """
    Remove placeholder seed fixtures once real API fixtures exist.

    Seed rows have no external_id/season; football-data rows have both.
    """
    comp = get_competition(slug)
    if not comp or comp.get("type") != "club":
        return 0

    real_count = (await db.execute(
        select(func.count(Match.id)).where(
            Match.competition_slug == slug,
            Match.external_id.isnot(None),
        )
    )).scalar() or 0
    if real_count == 0:
        return 0

    orphan_ids = list((await db.execute(
        select(Match.id).where(
            Match.competition_slug == slug,
            Match.external_id.is_(None),
            Match.season.is_(None),
        )
    )).scalars().all())
    if not orphan_ids:
        return 0

    await db.execute(delete(Prediction).where(Prediction.match_id.in_(orphan_ids)))
    await db.execute(delete(Odds).where(Odds.match_id.in_(orphan_ids)))
    result = await db.execute(delete(Match).where(Match.id.in_(orphan_ids)))
    await db.flush()
    return int(result.rowcount or 0)


async def reconcile_stale_matches(db: AsyncSession, slug: str) -> int:
    """
    Close out matches that should no longer be upcoming/live:
    - entire season past closing_date
    - kickoff was more than 6 hours ago but status never updated
    """
    comp = get_competition(slug)
    if not comp:
        return 0

    # match_time is stored as naive Beijing local time
    now = china_now().replace(tzinfo=None)
    closing = _parse_iso(comp.get("closing_date"))
    updated = 0

    if closing and now > closing:
        result = await db.execute(
            update(Match)
            .where(
                Match.competition_slug == slug,
                Match.status.in_(_ACTIVE),
            )
            .values(status=MATCH_FINISHED)
        )
        updated += int(result.rowcount or 0)
    else:
        stale_cutoff = now - MATCH_FINISH_BUFFER
        result = await db.execute(
            update(Match)
            .where(
                Match.competition_slug == slug,
                Match.status.in_(_ACTIVE),
                Match.match_time.isnot(None),
                Match.match_time < stale_cutoff,
            )
            .values(status=MATCH_FINISHED)
        )
        updated += int(result.rowcount or 0)

    if updated:
        await db.flush()
    return updated


async def clear_placeholder_scores(db: AsyncSession, slug: str) -> int:
    """Remove default 0:0 placeholders on matches that have not finished."""
    upcoming = match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)
    result = await db.execute(
        update(Match)
        .where(
            Match.competition_slug == slug,
            Match.status.in_(upcoming),
            Match.result_a == 0,
            Match.result_b == 0,
        )
        .values(result_a=None, result_b=None)
    )
    updated = int(result.rowcount or 0)
    if updated:
        await db.flush()
    return updated


async def reopen_prematurely_finished_matches(db: AsyncSession, slug: str) -> int:
    """Reset fixtures wrongly marked finished before kickoff ends (uses canonical kickoff)."""
    now = china_now().replace(tzinfo=None)
    rows = (
        await db.execute(
            select(Match).where(
                Match.competition_slug == slug,
                Match.status == MATCH_FINISHED,
                Match.match_time.isnot(None),
                Match.result_a.is_(None),
                Match.result_b.is_(None),
            )
        )
    ).scalars().all()
    updated = 0
    for m in rows:
        kickoff = effective_kickoff_naive(m)
        if kickoff is None or now >= kickoff + MATCH_FINISH_BUFFER:
            continue
        m.status = MATCH_UPCOMING
        updated += 1
    if updated:
        await db.flush()
    return updated


async def apply_confirmed_results(db: AsyncSession, slug: str) -> int:
    """Apply known final scores from worldcup_history into live fixtures."""
    if slug != "worldcup-2026":
        return 0
    from data.worldcup_history import HISTORICAL_MATCHES

    updated = 0
    for item in HISTORICAL_MATCHES:
        if item.get("year") != 2026:
            continue
        if item.get("result_a") is None or item.get("result_b") is None:
            continue
        row = await db.execute(
            select(Match).where(
                Match.competition_slug == slug,
                Match.team_a == item["team_a"],
                Match.team_b == item["team_b"],
                Match.stage == item.get("stage", "小组赛"),
            )
        )
        match = row.scalar_one_or_none()
        if not match:
            row = await db.execute(
                select(Match).where(
                    Match.competition_slug == slug,
                    Match.team_a == item["team_b"],
                    Match.team_b == item["team_a"],
                    Match.stage == item.get("stage", "小组赛"),
                )
            )
            match = row.scalar_one_or_none()
        if not match:
            continue
        match.result_a = int(item["result_a"])
        match.result_b = int(item["result_b"])
        match.status = MATCH_FINISHED
        from data.worldcup_venues import venue_for_match
        vn = venue_for_match(item["team_a"], item["team_b"])
        if vn:
            match.location, match.stadium = vn
        elif item.get("location"):
            match.location = item["location"]
        if not vn and item.get("stadium"):
            match.stadium = item["stadium"]
        updated += 1
    if updated:
        await db.flush()
    return updated


async def backfill_historical_odds(db: AsyncSession, slug: str) -> int:
    """Seed pre-match sporttery/euro odds from worldcup_history for fixtures missing Odds rows."""
    if slug != "worldcup-2026":
        return 0
    import json
    from db.models import Odds
    from data.worldcup_history import HISTORICAL_MATCHES

    updated = 0
    for item in HISTORICAL_MATCHES:
        if item.get("year") != 2026:
            continue
        if not item.get("score_odds") and not item.get("european"):
            continue
        row = await db.execute(
            select(Match).where(
                Match.competition_slug == slug,
                Match.team_a == item["team_a"],
                Match.team_b == item["team_b"],
                Match.stage == item.get("stage", "小组赛"),
            )
        )
        match = row.scalar_one_or_none()
        if not match:
            continue
        existing = (await db.execute(select(Odds).where(Odds.match_id == match.id))).scalar_one_or_none()
        if existing and existing.score_odds and existing.win_win:
            continue

        euro = item.get("european") or {}
        macau = item.get("macau") or {}
        score_odds = dict(item.get("score_odds") or {})
        score_odds["_meta"] = {"european": euro, "macau": macau}
        win_win = euro.get("win_win")
        draw = euro.get("draw")
        win_lose = euro.get("win_lose")

        if existing:
            if not existing.score_odds:
                existing.score_odds = json.dumps(score_odds, ensure_ascii=False)
            if not existing.win_win and win_win:
                existing.win_win = win_win
                existing.draw = draw
                existing.win_lose = win_lose
                existing.handicap = macau.get("handicap")
                existing.handicap_win = macau.get("handicap_win")
                existing.handicap_draw = macau.get("handicap_draw")
                existing.handicap_lose = macau.get("handicap_lose")
                existing.source = existing.source or "sporttery.cn+history"
            updated += 1
        else:
            db.add(Odds(
                match_id=match.id,
                win_win=win_win,
                draw=draw,
                win_lose=win_lose,
                handicap=macau.get("handicap"),
                handicap_win=macau.get("handicap_win"),
                handicap_draw=macau.get("handicap_draw"),
                handicap_lose=macau.get("handicap_lose"),
                score_odds=json.dumps(score_odds, ensure_ascii=False),
                source="worldcup_history",
            ))
            updated += 1
    if updated:
        await db.flush()
    return updated


async def refresh_predictions_for_matches(db: AsyncSession, match_ids: list[int]) -> int:
    """Force re-predict specific fixtures (e.g. after team-name repair)."""
    if not match_ids:
        return 0
    from service.prediction_service import PredictionService

    service = PredictionService()
    refreshed = 0
    for mid in match_ids:
        try:
            await service.predict_match(mid, db, model="auto", skip_cache=True)
            refreshed += 1
        except Exception as exc:
            logger.warning(f"Re-predict failed match {mid}: {exc}")
    if refreshed:
        await db.flush()
    return refreshed


async def refresh_missed_finished_predictions(db: AsyncSession, slug: str) -> int:
    """Re-predict finished fixtures whose stored picks missed the actual scoreline."""
    if slug != "worldcup-2026":
        return 0
    import json
    from db.models import Prediction
    from service.prediction_service import PredictionService

    def _predicted_lines(val) -> set[str]:
        if not val:
            return set()
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                return {val} if ":" in val else set()
        if isinstance(val, dict):
            lines = set(val.get("scores") or [])
            if val.get("upset"):
                lines.add(val["upset"])
            return lines
        if isinstance(val, list):
            return {s for s in val if s and ":" in str(s)}
        return set()

    rows = (await db.execute(
        select(Match).where(
            Match.competition_slug == slug,
            Match.status == MATCH_FINISHED,
            Match.result_a.isnot(None),
            Match.result_b.isnot(None),
        )
    )).scalars().all()

    service = PredictionService()
    refreshed = 0
    for match in rows:
        actual = f"{match.result_a}:{match.result_b}"
        pred = (await db.execute(
            select(Prediction).where(Prediction.match_id == match.id)
            .order_by(Prediction.create_time.desc())
        )).scalars().first()
        if pred and actual in _predicted_lines(pred.best_score):
            continue
        try:
            await service.predict_match(match.id, db, model="rule_engine", skip_cache=True)
            refreshed += 1
        except Exception as exc:
            logger.warning(f"Refresh prediction failed match {match.id}: {exc}")
    if refreshed:
        await db.flush()
    return refreshed


_last_result_sync_at: dict[str, float] = {}
_RESULT_SYNC_INTERVAL_SEC = 60
_LIVE_CACHE_TTL_SEC = 45


async def repair_canonical_kickoffs(db: AsyncSession, slug: str) -> int:
    """Align stored kickoff/status with official schedule (any status, incl. wrong finished)."""
    if slug != "worldcup-2026":
        return 0
    from data.worldcup_schedule_lookup import canonical_kickoff_beijing

    rows = (
        await db.execute(
            select(Match).where(
                Match.competition_slug == slug,
                Match.match_time.isnot(None),
            )
        )
    ).scalars().all()
    fixed = 0
    reopened = 0
    now = china_now().replace(tzinfo=None)
    for m in rows:
        canon = canonical_kickoff_beijing(m.team_a, m.team_b)
        if not canon:
            continue
        if m.match_time != canon:
            m.match_time = canon
            fixed += 1
        raw = normalize_match_status(m.status)
        if raw == MATCH_FINISHED and not match_has_recorded_score(m) and now < canon + MATCH_FINISH_BUFFER:
            m.status = MATCH_UPCOMING
            reopened += 1
    if fixed or reopened:
        await db.flush()
        logger.info(
            f"Canonical kickoff repair [{slug}]: {fixed} time(s), {reopened} reopened"
        )
    return fixed + reopened


def effective_kickoff_naive(match) -> datetime | None:
    """Kickoff for status inference; prefers canonical schedule when known."""
    kickoff = getattr(match, "match_time", None)
    if kickoff is None:
        return None
    if getattr(match, "competition_slug", None) == "worldcup-2026":
        ta = getattr(match, "team_a", None)
        tb = getattr(match, "team_b", None)
        if ta and tb:
            from data.worldcup_schedule_lookup import canonical_kickoff_beijing

            canon = canonical_kickoff_beijing(ta, tb)
            if canon:
                return canon
    return kickoff


def include_in_today_dashboard(match) -> bool:
    """Today section: canonical Beijing kickoff day + live or finished only."""
    from utils.datetime_helpers import china_today

    kt = effective_kickoff_naive(match)
    if kt is not None and kt.date() != china_today():
        return False
    return resolve_public_match_status(match) != MATCH_UPCOMING


async def sync_live_scores(db: AsyncSession, slug: str, *, network: bool = False) -> dict:
    """Fetch real-time scores from external APIs (football-data for World Cup)."""
    if slug != "worldcup-2026":
        return {"status": "skipped"}
    try:
        from crawler.worldcup_score_sync import sync_worldcup_scores_from_football_data
        return await sync_worldcup_scores_from_football_data(db, network=network)
    except Exception as exc:
        logger.warning(f"Live score sync failed [{slug}]: {exc}")
        return {"status": "failed", "error": str(exc)}


async def sync_match_results_throttled(db: AsyncSession, slug: str) -> int:
    """Apply history + cached live scores before serving match lists (fast, non-blocking)."""
    import time

    kickoffs = await repair_canonical_kickoffs(db, slug)
    applied = await apply_confirmed_results(db, slug)

    live_sync = {"updated": 0}
    if slug == "worldcup-2026":
        try:
            from service.write_guard import is_heavy_job_running
            heavy = is_heavy_job_running()
        except ImportError:
            heavy = False
        if not heavy:
            live_sync = await sync_live_scores(db, slug, network=False)
            kickoffs += await repair_canonical_kickoffs(db, slug)

    now = time.monotonic()
    elapsed = now - _last_result_sync_at.get(slug, 0)
    if elapsed < _LIVE_CACHE_TTL_SEC if slug == "worldcup-2026" else _RESULT_SYNC_INTERVAL_SEC:
        return kickoffs + int(applied) + int(live_sync.get("updated") or 0)
    _last_result_sync_at[slug] = now

    try:
        reconciled = await reconcile_stale_matches(db, slug)
    except OperationalError as exc:
        if "locked" in str(exc).lower():
            logger.warning(f"Result sync reconcile skipped for {slug} (SQLite locked)")
            await db.rollback()
            reconciled = 0
        else:
            raise
    total = applied + reconciled
    fd_updated = int(live_sync.get("updated") or 0)
    if total or fd_updated:
        logger.info(
            f"Match result sync [{slug}]: football_data={fd_updated}, "
            f"history={applied}, reconciled={reconciled}"
        )
    return kickoffs + total + fd_updated


async def maintain_competition_matches(db: AsyncSession, slug: str) -> dict:
    """Migrate legacy statuses, backfill seasons, cleanup seeds, reconcile stale."""
    from data.league_standings import ensure_league_standings_stats

    legacy = await migrate_legacy_statuses(db)
    seasons = await backfill_match_seasons(db, slug)
    team_seasons = await backfill_team_seasons(db, slug)
    removed = await cleanup_orphan_seed_matches(db, slug)
    deduped = await dedupe_duplicate_fixtures(db, slug)
    cleared_scores = await clear_placeholder_scores(db, slug)
    reopened = await reopen_prematurely_finished_matches(db, slug)
    confirmed = await apply_confirmed_results(db, slug)
    live_scores = await sync_live_scores(db, slug, network=True)
    from crawler.schedule_crawler import _build_expected_matches, _repair_misaligned_fixtures
    repaired_ids = await _repair_misaligned_fixtures(db, _build_expected_matches())
    fixtures_repaired = len(repaired_ids)
    if fixtures_repaired:
        confirmed += await apply_confirmed_results(db, slug)
    odds_backfill = await backfill_historical_odds(db, slug)
    repredicted = await refresh_predictions_for_matches(db, repaired_ids)
    predictions_refreshed = await refresh_missed_finished_predictions(db, slug)
    try:
        updated = await reconcile_stale_matches(db, slug)
    except OperationalError as exc:
        if "locked" in str(exc).lower():
            logger.warning(f"Stale match reconcile skipped for {slug} (SQLite locked)")
            await db.rollback()
            updated = 0
        else:
            raise
    try:
        standings = await ensure_league_standings_stats(db, slug)
    except OperationalError as exc:
        if "locked" in str(exc).lower():
            logger.warning(f"League standings skipped for {slug} (SQLite locked)")
            await db.rollback()
            standings = 0
        else:
            raise
    return {
        "legacy_migrated": legacy,
        "match_seasons": seasons,
        "team_seasons": team_seasons,
        "removed_orphans": removed,
        "deduped_fixtures": deduped,
        "cleared_placeholder_scores": cleared_scores,
        "reopened_premature": reopened,
        "confirmed_results_applied": confirmed,
        "live_scores_synced": live_scores,
        "fixtures_repaired": fixtures_repaired,
        "predictions_repredicted": repredicted,
        "historical_odds_backfilled": odds_backfill,
        "predictions_refreshed": predictions_refreshed,
        "status_updated": updated,
        "standings_recomputed": standings,
    }


def public_match_status(raw: str | None) -> str:
    """Normalize status for API responses."""
    return normalize_match_status(raw)


def match_has_recorded_score(match) -> bool:
    """True only when both goals are explicitly stored (not placeholder nulls)."""
    ra = getattr(match, "result_a", None)
    rb = getattr(match, "result_b", None)
    return ra is not None and rb is not None


def _now_beijing_naive() -> datetime:
    return china_now().replace(tzinfo=None)


def resolve_public_match_status(match) -> str:
    """Effective status: scores and kickoff window override stale DB flags."""
    raw = normalize_match_status(getattr(match, "status", None))
    if raw == MATCH_LIVE:
        return MATCH_LIVE
    if match_has_recorded_score(match):
        return MATCH_FINISHED
    kickoff = effective_kickoff_naive(match)
    if kickoff is not None:
        now = _now_beijing_naive()
        if now >= kickoff + MATCH_FINISH_BUFFER:
            return MATCH_FINISHED
        if kickoff <= now < kickoff + MATCH_FINISH_BUFFER:
            return MATCH_LIVE
        return MATCH_UPCOMING
    if raw == MATCH_FINISHED:
        return MATCH_FINISHED
    return raw if raw in (MATCH_UPCOMING, MATCH_LIVE, MATCH_FINISHED) else MATCH_UPCOMING
