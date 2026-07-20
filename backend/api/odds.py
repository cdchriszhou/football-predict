import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from db.models import Odds, Match
from utils.response import success
from api.auth import get_current_user
from api.deps import require_competition_entitlement
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])


def _parse_odds_json(val):
    """Parse JSON odds field, return empty dict on failure"""
    if val is None:
        return {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _european_from_row(meta: dict, odds: Odds) -> dict | None:
    """Resolve European 1X2 from _meta or top-level columns (never sporttery-only rows)."""
    european = meta.get("european") if meta else None
    if european and european.get("win_win"):
        return european
    src = (odds.source or "").lower()
    if "the-odds-api" in src and odds.win_win:
        return {
            "win_win": odds.win_win,
            "draw": odds.draw,
            "win_lose": odds.win_lose,
            "over_under": odds.over_under,
            "over_odds": odds.over_odds,
            "under_odds": odds.under_odds,
            "source": odds.source or "the-odds-api",
        }
    return None


def _macau_for_display(meta: dict, odds: Odds) -> dict | None:
    """Return Macau odds for UI; derive from European when API spreads are missing."""
    macau = (meta or {}).get("macau") or {}
    if macau.get("win_win") and macau.get("handicap"):
        return macau

    european = _european_from_row(meta or {}, odds)
    if not european or not european.get("win_win"):
        return macau or None

    from service.odds_fusion import derive_macau_from_european

    return derive_macau_from_european(european)


def _serialize_odds(odds: Optional[Odds], match_id: int) -> dict:
    """Serialize odds row; split score_odds meta for market vs sporttery tabs."""
    empty = {
        "match_id": match_id,
        "win_win": None, "draw": None, "win_lose": None,
        "handicap": None, "handicap_win": None, "handicap_draw": None, "handicap_lose": None,
        "over_under": None, "over_odds": None, "under_odds": None,
        "score_odds": {}, "half_full_odds": {},
        "european": None, "macau": None, "sporttery": None, "sporttery_meta": None,
        "source": None, "update_time": None,
    }
    if not odds:
        return empty

    score_raw = _parse_odds_json(odds.score_odds)
    meta = {}
    if isinstance(score_raw, dict):
        meta = score_raw.pop("_meta", {}) or {}

    european = _european_from_row(meta, odds)
    macau = _macau_for_display(meta, odds)
    handicap = odds.handicap
    handicap_win = odds.handicap_win
    handicap_draw = odds.handicap_draw
    handicap_lose = odds.handicap_lose
    if macau and not handicap:
        handicap = macau.get("handicap")
        handicap_win = macau.get("handicap_win")
        handicap_draw = macau.get("handicap_draw")
        handicap_lose = macau.get("handicap_lose")

    return {
        "match_id": match_id,
        "win_win": odds.win_win,
        "draw": odds.draw,
        "win_lose": odds.win_lose,
        "handicap": handicap,
        "handicap_win": handicap_win,
        "handicap_draw": handicap_draw,
        "handicap_lose": handicap_lose,
        "over_under": odds.over_under,
        "over_odds": odds.over_odds,
        "under_odds": odds.under_odds,
        "score_odds": score_raw,
        "half_full_odds": _parse_odds_json(odds.half_full_odds),
        "european": european,
        "macau": macau,
        "sporttery": None,
        "sporttery_meta": meta.get("sporttery"),
        "source": odds.source,
        "update_time": odds.update_time.isoformat() if odds.update_time else None,
    }


@router.post("/batch")
async def get_odds_batch(
    match_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Batch-fetch lottery-style odds for multiple matches (for schedule list)."""
    if not match_ids:
        return success({})

    odds_rows = (await db.execute(
        select(Odds).where(Odds.match_id.in_(match_ids))
    )).scalars().all()
    odds_by_match = {o.match_id: o for o in odds_rows}
    matches = (await db.execute(
        select(Match).where(Match.id.in_(match_ids))
    )).scalars().all()
    match_by_id = {m.id: m for m in matches}

    from crawler.sporttery_client import fetch_sporttery_on_sale
    from service.sporttery_resolve import enrich_serialized_odds

    sporttery_pool = await fetch_sporttery_on_sale(force_refresh=True)

    result = {}
    for mid in match_ids:
        o = odds_by_match.get(mid)
        m = match_by_id.get(mid)
        if not o and not m:
            continue
        serialized = _serialize_odds(o, mid) if o else _serialize_odds(None, mid)
        if m:
            serialized = await enrich_serialized_odds(
                db, m, serialized, pool=sporttery_pool, odds_row=o,
            )
        st = serialized.get("sporttery") or {}
        has_sporttery = bool(
            st.get("win_win")
            or st.get("handicap_win")
            or st.get("handicap_draw")
            or st.get("handicap_lose")
            or st.get("score_odds")
        )
        has_data = (
            serialized.get("win_win")
            or serialized.get("european")
            or serialized.get("macau")
            or has_sporttery
        )
        if not has_data:
            continue
        result[mid] = serialized
    return success(result)


@router.get("/{match_id}")
async def get_odds(match_id: int, db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_user)):
    odds = (await db.execute(
        select(Odds).where(Odds.match_id == match_id).order_by(Odds.update_time.desc())
    )).scalar_one_or_none()
    match = (await db.execute(
        select(Match).where(Match.id == match_id)
    )).scalar_one_or_none()

    if not odds:
        serialized = _serialize_odds(None, match_id)
    else:
        serialized = _serialize_odds(odds, match_id)

    if match:
        from crawler.sporttery_client import fetch_sporttery_on_sale
        from service.sporttery_resolve import enrich_serialized_odds
        sporttery_pool = await fetch_sporttery_on_sale(force_refresh=True)
        serialized = await enrich_serialized_odds(
            db, match, serialized, pool=sporttery_pool, odds_row=odds,
        )

    return success(serialized)


@router.get("/latest/list")
async def get_latest_odds_changes(db: AsyncSession = Depends(get_db), current_user: str = Depends(get_current_user)):
    """Latest odds data for all active matches"""
    from sqlalchemy import and_

    matches = (await db.execute(
        select(Match).where(Match.status.in_(match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE)))
    )).scalars().all()

    result = []
    for match in matches:
        odds = (await db.execute(
            select(Odds).where(Odds.match_id == match.id).order_by(Odds.update_time.desc())
        )).scalar_one_or_none()

        result.append({
            "match_id": match.id,
            "team_a": match.team_a, "team_b": match.team_b,
            "stage": match.stage,
            "match_time": match.match_time.isoformat() if match.match_time else None,
            "win_win": odds.win_win if odds else None,
            "draw": odds.draw if odds else None,
            "win_lose": odds.win_lose if odds else None,
            "handicap": odds.handicap if odds else None,
            "update_time": odds.update_time.isoformat() if odds and odds.update_time else None
        })

    return success(result)
