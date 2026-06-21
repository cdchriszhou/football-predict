"""Keep stored predictions, W/D/L, score picks, and reason text in sync."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Match, Prediction
from data.status_constants import MATCH_UPCOMING
from utils.logger import logger
from utils.score_prediction import parse_best_score_payload, reconcile_prediction_view

_WDL_NOTE_PREFIX = "[胜平负校正]"
_SCORE_NOTE_PREFIX = "[热门比分]"
_AUTO_NOTE_PREFIXES = (_WDL_NOTE_PREFIX, _SCORE_NOTE_PREFIX, "[校验]")


def encode_best_score(scores: list | None, upset: str | None = None) -> str:
    from utils.score_prediction import normalize_score_prediction

    clean = normalize_score_prediction(scores, upset)["best_scores"]
    upset_val = upset if upset and upset != "?" else None
    if upset_val:
        return json.dumps({"scores": clean, "upset": upset_val}, ensure_ascii=False)
    return json.dumps(clean or ["?"], ensure_ascii=False)


def wdl_score_mismatch(
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
    best_scores: list[str] | None,
) -> bool:
    from service.score_pick import _score_outcome, dominant_wdl_outcome

    picks = [s for s in (best_scores or []) if s and s != "?"]
    if not picks:
        return False
    dom = dominant_wdl_outcome(win_rate, draw_rate, lose_rate)
    return _score_outcome(picks[0]) != dom


def _strip_auto_notes(reason: str | None) -> str:
    if not reason:
        return ""
    parts = [p.strip() for p in reason.split("|")]
    kept = [
        p for p in parts
        if p and not any(p.startswith(prefix) for prefix in _AUTO_NOTE_PREFIXES)
    ]
    return " | ".join(kept)


def sync_reason_with_view(
    reason: str | None,
    team_a: str,
    team_b: str,
    view: dict,
) -> str:
    """Rewrite auto-generated tail so narrative matches reconciled W/D/L and scores."""
    from service.score_pick import dominant_wdl_outcome

    base = _strip_auto_notes(reason)
    picks = [s for s in (view.get("best_scores") or []) if s and s != "?"]
    w = float(view.get("win_rate") or 0)
    d = float(view.get("draw_rate") or 0)
    l = float(view.get("lose_rate") or 0)
    dom = dominant_wdl_outcome(w, d, l)
    outcome_zh = {
        "win": f"{team_a}胜",
        "lose": f"{team_b}胜",
        "draw": "平局",
    }[dom]
    primary = picks[0] if picks else "?"
    wdl_note = (
        f"{_WDL_NOTE_PREFIX} {outcome_zh} "
        f"{w:.1f}%/{d:.1f}%/{l:.1f}%（推荐 {team_a} {primary}）"
    )
    score_note = f"{_SCORE_NOTE_PREFIX} {' / '.join(picks)}" if picks else ""
    upset = view.get("upset_score")
    if score_note and upset and upset != "?":
        score_note += f"（冷门 {upset}）"
    tail = " | ".join(x for x in (wdl_note, score_note) if x)
    return f"{base} | {tail}" if base else tail


def build_repaired_view(pred: Prediction, match: Match) -> tuple[dict, bool]:
    """Reconcile W/D/L with stored score picks and refresh reason tail."""
    payload = parse_best_score_payload(getattr(pred, "best_score", None))
    wr = float(getattr(pred, "win_rate", None) or 0)
    lr = float(getattr(pred, "lose_rate", None) or 0)
    dr_raw = getattr(pred, "draw_rate", None)
    dr = float(dr_raw) if dr_raw is not None else max(0.0, 100.0 - wr - lr)
    old_wr = wr
    old_lr = lr
    view = reconcile_prediction_view(
        payload["scores"],
        payload.get("upset"),
        old_wr,
        dr,
        lr,
    )
    reason = getattr(pred, "reason", None)
    new_reason = sync_reason_with_view(reason, match.team_a, match.team_b, view)
    view["reason"] = new_reason

    encoded = encode_best_score(view["best_scores"], view.get("upset_score"))
    best_score_raw = getattr(pred, "best_score", None)
    old_encoded = best_score_raw if isinstance(best_score_raw, str) else json.dumps(
        best_score_raw, ensure_ascii=False
    ) if best_score_raw is not None else ""

    changed = (
        abs(float(view["win_rate"]) - old_wr) > 0.05
        or abs(float(view["lose_rate"]) - old_lr) > 0.05
        or abs(float(view["draw_rate"]) - dr) > 0.05
        or wdl_score_mismatch(old_wr, dr, old_lr, payload["scores"])
        or encoded != old_encoded
        or new_reason != (reason or "")
    )
    return view, changed


def apply_view_to_prediction(pred: Prediction, view: dict) -> None:
    pred.win_rate = view["win_rate"]
    pred.draw_rate = view["draw_rate"]
    pred.lose_rate = view["lose_rate"]
    pred.best_score = encode_best_score(view["best_scores"], view.get("upset_score"))
    if view.get("reason") is not None:
        pred.reason = view["reason"]


def repair_prediction_record(pred: Prediction, match: Match) -> bool:
    """In-memory repair for one prediction row. Returns True if fields changed."""
    view, changed = build_repaired_view(pred, match)
    if changed:
        apply_view_to_prediction(pred, view)
    return changed


async def invalidate_prediction_cache(match_id: int) -> None:
    try:
        from db.redis_client import get_redis
        redis = await get_redis()
        if redis is None:
            return
        keys = []
        async for key in redis.scan_iter(match=f"prediction:{match_id}:*"):
            keys.append(key)
        if keys:
            await redis.delete(*keys)
    except Exception as exc:
        logger.debug("Prediction cache invalidate skipped match %s: %s", match_id, exc)


async def ensure_prediction_consistency(
    db: AsyncSession,
    pred: Prediction,
    match: Match,
    *,
    persist: bool = True,
) -> dict:
    """Return reconciled view; optionally persist fixes to DB and clear cache."""
    view, changed = build_repaired_view(pred, match)
    if changed and persist:
        apply_view_to_prediction(pred, view)
        await invalidate_prediction_cache(match.id)
        logger.info(
            "Repaired prediction consistency match=%s %s vs %s",
            match.id, match.team_a, match.team_b,
        )
    return view


async def repair_predictions_for_matches(db: AsyncSession, match_ids: list[int]) -> int:
    if not match_ids:
        return 0
    rows = (
        await db.execute(
            select(Prediction, Match)
            .join(Match, Prediction.match_id == Match.id)
            .where(Match.id.in_(match_ids))
            .order_by(Prediction.match_id, Prediction.create_time.desc())
        )
    ).all()
    seen: set[int] = set()
    fixed = 0
    for pred, match in rows:
        if match.id in seen:
            continue
        seen.add(match.id)
        view, changed = build_repaired_view(pred, match)
        if not changed:
            continue
        apply_view_to_prediction(pred, view)
        await invalidate_prediction_cache(match.id)
        fixed += 1
    if fixed:
        await db.flush()
        logger.info("Prediction repair for %d match(es): %s", fixed, match_ids[:8])
    return fixed


async def repair_stale_predictions(
    db: AsyncSession,
    slug: str,
    *,
    upcoming_only: bool = True,
) -> int:
    """Scan stored predictions and fix W/D/L vs score / reason drift."""
    query = (
        select(Prediction, Match)
        .join(Match, Prediction.match_id == Match.id)
        .where(Match.competition_slug == slug)
        .order_by(Prediction.match_id, Prediction.create_time.desc())
    )
    if upcoming_only:
        query = query.where(Match.status == MATCH_UPCOMING)
    rows = (await db.execute(query)).all()
    seen: set[int] = set()
    fixed = 0
    for pred, match in rows:
        if match.id in seen:
            continue
        seen.add(match.id)
        view, changed = build_repaired_view(pred, match)
        if not changed:
            continue
        apply_view_to_prediction(pred, view)
        await invalidate_prediction_cache(match.id)
        fixed += 1
    if fixed:
        await db.flush()
        logger.info("Stale prediction repair [%s]: %d fixture(s)", slug, fixed)
    return fixed
