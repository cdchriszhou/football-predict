import json

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from db.models import Prediction, Match, Team, Odds
from db.redis_client import cache_get, cache_set, cache_delete
from service.prediction_service import PredictionService, team_to_dict, prepare_fused_odds, infer_matchday
from service.calibration_service import CalibratedRuleEngine
from service.score_backtest import compute_score_backtest, get_or_compute_daily_report
from service.score_pick import (
    run_full_score_pipeline,
    score_matches_pick,
)
from service.match_context import build_group_context
from data.worldcup_group_standings import load_group_standings
from utils.response import success
from api.auth import get_current_user
from api.competitions import resolve_competition
from api.deps import require_competition_entitlement
from data.status_constants import MATCH_FINISHED
from utils.score_prediction import (
    normalize_score_prediction,
    parse_best_score_payload,
    reconcile_prediction_view,
)
from service.prediction_consistency import ensure_prediction_consistency

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])
prediction_service = PredictionService()
rule_engine = CalibratedRuleEngine()


def _parse_best_score(val):
    """Parse best_score from DB. New format is JSON array, old format is plain string."""
    return parse_best_score_payload(val)["scores"]


def _parse_upset_score(val):
    upset = parse_best_score_payload(val)["upset"]
    return upset if upset and upset != "?" else None


async def _normalized_prediction_scores(
    pred: Prediction,
    match: Match,
    db: AsyncSession,
    *,
    persist: bool = True,
    crs: dict | None = None,
    odds_row: Odds | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> dict:
    """Return stored score picks; auto-repair and persist when W/D/L drifted."""
    return await ensure_prediction_consistency(db, pred, match, persist=persist)


@router.post("/batch")
async def get_predictions_batch(
    match_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """Get latest predictions for multiple matches, using rule engine for missing ones"""
    if not match_ids:
        return success({})

    matches = (await db.execute(
        select(Match).where(Match.id.in_(match_ids))
    )).scalars().all()
    matches_by_id = {m.id: m for m in matches}

    all_teams = set()
    for m in matches:
        all_teams.add(m.team_a)
        all_teams.add(m.team_b)
    teams = (await db.execute(
        select(Team).where(
            Team.competition_slug.in_({m.competition_slug for m in matches}),
            Team.name.in_(all_teams),
        )
    )).scalars().all() if matches else []
    teams_by_key = {(t.competition_slug, t.name): t for t in teams}

    odds_rows = (await db.execute(
        select(Odds).where(Odds.match_id.in_(match_ids)).order_by(Odds.id.desc())
    )).scalars().all()
    odds_by_match: dict[int, Odds] = {}
    for row in odds_rows:
        odds_by_match.setdefault(row.match_id, row)

    # Check which predictions already exist in DB (latest first per match)
    predictions = (await db.execute(
        select(Prediction).where(Prediction.match_id.in_(match_ids))
        .order_by(Prediction.match_id, Prediction.create_time.desc())
    )).scalars().all()

    existing_ids = set()
    result = {}
    for p in predictions:
        if p.match_id not in result:
            match = matches_by_id.get(p.match_id)
            odds_row = odds_by_match.get(p.match_id)
            crs = None
            if odds_row and match:
                fused = prepare_fused_odds(odds_row, match.team_a, match.team_b)
                crs = (fused or {}).get("score_odds")
            if not match:
                continue
            norm = await _normalized_prediction_scores(p, match, db, persist=True)
            result[p.match_id] = {
                **norm,
                "confidence": p.confidence,
                "reason": norm.get("reason") or p.reason,
            }
            existing_ids.add(p.match_id)

    # For missing matches, use calibrated rule engine (with CRS when odds exist)
    missing_ids = [mid for mid in match_ids if mid not in existing_ids]
    if missing_ids:
        for mid in missing_ids:
            match = matches_by_id.get(mid)
            if not match:
                continue
            ta = teams_by_key.get((match.competition_slug, match.team_a))
            tb = teams_by_key.get((match.competition_slug, match.team_b))
            ta_dict = team_to_dict(ta) if ta else {"name": match.team_a}
            tb_dict = team_to_dict(tb) if tb else {"name": match.team_b}

            odds_row = odds_by_match.get(mid)
            odds_dict = prepare_fused_odds(odds_row, match.team_a, match.team_b) if odds_row else None
            score_odds = (odds_dict or {}).get("score_odds") or None

            matchday = await infer_matchday(match, db)
            standings = None
            if match.stage == "小组赛" and match.group_name:
                standings = await load_group_standings(
                    db, match.competition_slug, match.group_name, match.match_time,
                )
            group_context = build_group_context(
                match.stage, match.group_name or "", matchday,
                match.team_a, match.team_b,
                ta_dict.get("rank", 50), tb_dict.get("rank", 50),
                location=match.location or "",
                standings=standings,
            )
            if match.stage == "小组赛" and match.group_name and matchday >= 2:
                from data.worldcup_group_standings import load_group_fifa_ranks
                from service.score_context import enrich_knockout_outlook
                from service.score_context import _R16_RUNNER_VS_WINNER, _R16_WINNER_VS_RUNNER

                letter = (match.group_name or "").strip().upper()
                paired: set[str] = set()
                if letter in _R16_WINNER_VS_RUNNER:
                    paired.add(_R16_WINNER_VS_RUNNER[letter])
                if letter in _R16_RUNNER_VS_WINNER:
                    paired.add(_R16_RUNNER_VS_WINNER[letter])
                paired_ranks: dict[str, list[int]] = {}
                for pg in paired:
                    paired_ranks[pg] = await load_group_fifa_ranks(
                        db, match.competition_slug, pg,
                    )
                enrich_knockout_outlook(
                    group_context,
                    match.team_a,
                    match.team_b,
                    int(ta_dict.get("rank") or 50),
                    int(tb_dict.get("rank") or 50),
                    paired_group_ranks=paired_ranks,
                )

            if score_odds:
                r = rule_engine.evaluate(
                    ta_dict, tb_dict,
                    odds=odds_dict,
                    score_odds=score_odds,
                    group_context=group_context,
                )
                best, upset, _, _ = run_full_score_pipeline(
                    score_odds,
                    win_rate=r.win_rate,
                    draw_rate=r.draw_rate,
                    lose_rate=r.lose_rate,
                    expected_a=r.expected_a,
                    expected_b=r.expected_b,
                    model_scores=r.best_scores,
                    stage=match.stage,
                    sp_win=(odds_dict or {}).get("win_win"),
                    sp_lose=(odds_dict or {}).get("win_lose"),
                    sp_draw=(odds_dict or {}).get("draw"),
                    handicap=(odds_dict or {}).get("handicap"),
                    rank_a=ta_dict.get("rank"),
                    rank_b=tb_dict.get("rank"),
                    group_context=group_context,
                    odds_dict=odds_dict,
                    rule_result=r,
                    team_a=ta_dict,
                    team_b=tb_dict,
                )
                norm = normalize_score_prediction(best, upset)
                view = reconcile_prediction_view(
                    norm["best_scores"],
                    norm.get("upset_score"),
                    r.win_rate,
                    r.draw_rate,
                    r.lose_rate,
                )
                from service.prediction_consistency import sync_reason_with_view
                view["reason"] = sync_reason_with_view(None, match.team_a, match.team_b, view)
                result[mid] = {**view, "confidence": 0.5}
            else:
                r = rule_engine.evaluate(ta_dict, tb_dict, group_context=group_context)
                norm = normalize_score_prediction(
                    r.best_scores,
                    r.upset_score if r.upset_score != "?" else None,
                )
                view = reconcile_prediction_view(
                    norm["best_scores"],
                    norm.get("upset_score"),
                    r.win_rate,
                    r.draw_rate,
                    r.lose_rate,
                )
                from service.prediction_consistency import sync_reason_with_view
                view["reason"] = sync_reason_with_view(None, match.team_a, match.team_b, view)
                result[mid] = {**view, "confidence": 0.5}

    return success(result)


@router.get("/backtest")
async def get_score_backtest(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Replay CRS score pipeline on finished matches to validate algorithm reliability."""
    comp_slug = resolve_competition(competition)
    data = await compute_score_backtest(db, comp_slug)
    return success(data)


@router.get("/backtest/daily")
async def get_daily_score_backtest(
    competition: str = Query("worldcup-2026"),
    days: int = Query(14, ge=1, le=90),
    refresh: bool = Query(False, description="跳过缓存强制重算"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Post-match daily score backtest report for dashboard."""
    comp_slug = resolve_competition(competition)
    data = await get_or_compute_daily_report(db, comp_slug, days=days, force=refresh)
    return success(data)


@router.get("/accuracy/stats")
async def get_accuracy(
    competition: str = Query("worldcup-2026"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Calculate prediction accuracy for completed matches"""
    from datetime import datetime, timedelta
    comp_slug = resolve_competition(competition)
    cutoff = datetime.now() - timedelta(days=days)

    predictions = (await db.execute(
        select(Prediction, Match).join(Match, Prediction.match_id == Match.id).where(
            Match.competition_slug == comp_slug,
            Match.status == MATCH_FINISHED,
            Prediction.create_time >= cutoff
        )
    )).all()

    match_ids = [match.id for _, match in predictions]
    odds_by_match: dict[int, Odds] = {}
    if match_ids:
        odds_rows = (await db.execute(
            select(Odds).where(Odds.match_id.in_(match_ids)).order_by(Odds.id.desc())
        )).scalars().all()
        for row in odds_rows:
            odds_by_match.setdefault(row.match_id, row)

    total = len(predictions)
    if total == 0:
        return success({"total": 0, "accuracy": 0, "message": "No data for accuracy analysis"})

    correct_results = 0
    correct_scores = 0
    confidence_sum = 0.0

    for pred, match in predictions:
        # Skip matches without recorded scores (e.g. finished but not yet synced)
        if match.result_a is None or match.result_b is None:
            continue

        view = await ensure_prediction_consistency(db, pred, match, persist=True)
        wr, dr, lr = view["win_rate"], view["draw_rate"], view["lose_rate"]

        actual_winner = "a" if match.result_a > match.result_b else ("b" if match.result_b > match.result_a else "draw")
        pred_winner = "a" if wr > lr and wr > dr else ("b" if lr > wr and lr > dr else "draw")

        if actual_winner == pred_winner:
            correct_results += 1

        predicted_scores = list(view.get("best_scores") or [])
        upset = view.get("upset_score")
        if upset:
            predicted_scores.append(upset)
        actual_score = f"{match.result_a}:{match.result_b}"
        odds_row = odds_by_match.get(match.id)
        crs = None
        if odds_row:
            fused = prepare_fused_odds(odds_row, match.team_a, match.team_b)
            crs = (fused or {}).get("score_odds")
        if any(score_matches_pick(actual_score, p, crs) for p in predicted_scores if p):
            correct_scores += 1

        confidence_sum += pred.confidence or 0.8

    return success({
        "total": total,
        "result_accuracy": round(correct_results / total * 100, 1),
        "score_accuracy": round(correct_scores / total * 100, 1),
        "avg_confidence": round(confidence_sum / total, 2)
    })


@router.get("/{match_id}")
async def get_prediction(
    match_id: int,
    model: str = Query("auto", description="预测模型，auto=自动检测所有已配置模型"),
    refresh: bool = Query(False, description="强制刷新"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    model_key = model or "auto"

    if not refresh:
        cached = await cache_get(f"prediction:{match_id}:{model_key}")
        if cached:
            from service.prediction_consistency import sync_reason_with_view
            view = reconcile_prediction_view(
                cached.get("best_scores"),
                cached.get("upset_score"),
                cached.get("win_rate") or 50.0,
                cached.get("draw_rate") or 28.0,
                cached.get("lose_rate") or 50.0,
            )
            ta = cached.get("team_a") or ""
            tb = cached.get("team_b") or ""
            if ta and tb:
                view["reason"] = sync_reason_with_view(cached.get("reason"), ta, tb, view)
            return success({**cached, **view})

        # DB snapshot only for fused auto mode; single-model views must re-run LLM.
        if model_key == "auto":
            pred = (await db.execute(
                select(Prediction).where(Prediction.match_id == match_id).order_by(Prediction.create_time.desc()).limit(1)
            )).scalar_one_or_none()

            if pred:
                match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
                if match:
                    norm = await _normalized_prediction_scores(pred, match, db, persist=True)
                    return success({
                        "match_id": match_id,
                        "team_a": match.team_a,
                        "team_b": match.team_b,
                        "stage": match.stage,
                        **norm,
                        "handicap_result": pred.handicap_result,
                        "total_goals": pred.total_goals,
                        "reason": norm.get("reason") or pred.reason,
                        "model_used": pred.model_used,
                        "confidence": pred.confidence,
                        "create_time": pred.create_time.isoformat() if pred.create_time else None,
                    })

    # Generate fresh prediction (per-model cache key inside service)
    actual_model = None if model_key == "auto" else model_key
    result = await prediction_service.predict_match(match_id, db, actual_model, skip_cache=refresh)
    if not result:
        raise HTTPException(status_code=404, detail="比赛不存在")

    return success(result)
