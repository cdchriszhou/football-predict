"""Resolve sporttery.cn on-sale odds for DB fixtures (live API + cache)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from crawler.sporttery_client import (
    fetch_sporttery_on_sale,
    find_sporttery_match,
    find_sporttery_match_by_id,
    sporttery_row_has_sale_data,
    to_db_odds,
)
from data.competitions import get_competition, league_hints_for
from db.models import Match, Odds


def _parse_odds_json(val) -> dict:
    if val is None:
        return {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _is_sporttery_source(source: str | None) -> bool:
    return bool(source and "sporttery" in source.lower())


def _sporttery_response_from_row(row: dict, st_raw: dict | None = None) -> dict:
    return {
        "win_win": row["win_win"],
        "draw": row["draw"],
        "win_lose": row["win_lose"],
        "handicap": row.get("handicap"),
        "handicap_win": row.get("handicap_win"),
        "handicap_draw": row.get("handicap_draw"),
        "handicap_lose": row.get("handicap_lose"),
        "over_under": row.get("over_under"),
        "over_odds": row.get("over_odds"),
        "under_odds": row.get("under_odds"),
        "score_odds": row.get("score_odds") or {},
        "half_full_odds": row.get("half_full_odds") or {},
        "sporttery_meta": {
            "match_id": row.get("sporttery_match_id"),
            "match_num": row.get("sporttery_match_num"),
            "league": (st_raw or {}).get("league"),
        },
        "source": "sporttery.cn",
        "update_time": row.get("update_time").isoformat() if row.get("update_time") else None,
    }


def _stored_sporttery_match_id(odds_row: Odds | None) -> int | str | None:
    if not odds_row:
        return None
    score_raw = _parse_odds_json(odds_row.score_odds)
    if not isinstance(score_raw, dict):
        return None
    meta = score_raw.get("_meta") or {}
    st_meta = meta.get("sporttery") or {}
    return st_meta.get("match_id")


def _sync_top_level_from_sporttery(serialized: dict, sporttery: dict) -> None:
    """Keep legacy top-level fields aligned with live sporttery block."""
    if not sporttery.get("win_win"):
        return
    for key in (
        "win_win", "draw", "win_lose",
        "handicap", "handicap_win", "handicap_draw", "handicap_lose",
        "over_under", "over_odds", "under_odds",
    ):
        if sporttery.get(key) is not None:
            serialized[key] = sporttery[key]
    if sporttery.get("score_odds"):
        serialized["score_odds"] = sporttery["score_odds"]
    if sporttery.get("half_full_odds"):
        serialized["half_full_odds"] = sporttery["half_full_odds"]
    if sporttery.get("update_time"):
        serialized["update_time"] = sporttery["update_time"]
    src = serialized.get("source") or ""
    if "sporttery" not in src.lower():
        serialized["source"] = "sporttery.cn" if not src else f"sporttery.cn+{src}"


def sporttery_payload_from_db(odds: Odds, team_a: str, team_b: str) -> dict | None:
    """Build sporttery view from a stored Odds row when source includes sporttery.cn."""
    if not odds or not _is_sporttery_source(odds.source):
        return None
    score_raw = _parse_odds_json(odds.score_odds)
    meta = score_raw.pop("_meta", {}) if isinstance(score_raw, dict) else {}
    st_meta = meta.get("sporttery") if isinstance(meta, dict) else None
    return {
        "win_win": odds.win_win,
        "draw": odds.draw,
        "win_lose": odds.win_lose,
        "handicap": odds.handicap,
        "handicap_win": odds.handicap_win,
        "handicap_draw": odds.handicap_draw,
        "handicap_lose": odds.handicap_lose,
        "over_under": odds.over_under,
        "over_odds": odds.over_odds,
        "under_odds": odds.under_odds,
        "score_odds": score_raw if isinstance(score_raw, dict) else {},
        "half_full_odds": _parse_odds_json(odds.half_full_odds),
        "sporttery_meta": st_meta,
        "source": "sporttery.cn",
        "update_time": odds.update_time.isoformat() if odds.update_time else None,
    }


async def resolve_sporttery_for_match(
    match: Match,
    *,
    pool: list[dict] | None = None,
    odds_row: Odds | None = None,
) -> dict | None:
    """Return sporttery odds: prefer live on-sale API, else last stored pre-match snapshot."""
    hints = league_hints_for(match.competition_slug) or ("世界", "世界杯", "World Cup", "FIFA")
    sporttery_pool = pool if pool is not None else await fetch_sporttery_on_sale()
    stored_id = _stored_sporttery_match_id(odds_row)
    st_raw = find_sporttery_match_by_id(stored_id, sporttery_pool)
    if st_raw:
        home, away = st_raw["home_team"], st_raw["away_team"]
        from crawler.sporttery_client import normalize_team_name
        our_a, our_b = normalize_team_name(match.team_a), normalize_team_name(match.team_b)
        if not (
            (our_a == home and our_b == away) or (our_a == away and our_b == home)
        ):
            st_raw = None
    if not st_raw:
        st_raw = find_sporttery_match(
            match.team_a,
            match.team_b,
            match.match_time,
            sporttery_pool,
            league_hints=hints,
            sporttery_match_id=stored_id,
        )
    live_row = to_db_odds(st_raw, match.team_a, match.team_b) if st_raw else None
    cached = sporttery_payload_from_db(odds_row, match.team_a, match.team_b) if odds_row else None

    if live_row and sporttery_row_has_sale_data(live_row):
        payload = _sporttery_response_from_row(live_row, st_raw)
        payload["on_sale"] = True
        return payload

    if cached and sporttery_row_has_sale_data(cached):
        cached["on_sale"] = False
        return cached

    return None


async def enrich_serialized_odds(
    db: AsyncSession,
    match: Match,
    serialized: dict,
    *,
    pool: list[dict] | None = None,
    odds_row: Odds | None = None,
) -> dict:
    """Attach live `sporttery` block; sync top-level SPF/RQ when on sale."""
    sporttery = await resolve_sporttery_for_match(
        match, pool=pool, odds_row=odds_row,
    )
    if sporttery:
        serialized["sporttery"] = sporttery
        serialized["sporttery_meta"] = sporttery.get("sporttery_meta") or serialized.get("sporttery_meta")
        if sporttery.get("on_sale"):
            _sync_top_level_from_sporttery(serialized, sporttery)
    return serialized
