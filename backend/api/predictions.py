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
    canonical_score_recommendations,
)
from service.match_context import build_group_context
from data.worldcup_group_standings import load_group_standings
from utils.response import success
from api.auth import get_current_user
from api.competitions import resolve_competition
from api.deps import require_competition_entitlement
from data.status_constants import MATCH_FINISHED
from utils.score_prediction import normalize_score_prediction

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])
prediction_service = PredictionService()
rule_engine = CalibratedRuleEngine()


def _parse_best_score_payload(val):
    """Parse best_score DB field — supports array, object, or legacy string."""
    if val is None:
        return {"scores": ["?"], "upset": None}
    if isinstance(val, dict):
        scores = val.get("scores") or ["?"]
        upset = val.get("upset")
        return {"scores": scores, "upset": upset}
    if isinstance(val, list):
        return {"scores": val, "upset": None}
    if isinstance(val, str):
        if val.startswith("{") or val.startswith("["):
            try:
                parsed = json.loads(val)
                return _parse_best_score_payload(parsed)
            except json.JSONDecodeError:
                pass
        return {"scores": [val] if val != "?" else ["?"], "upset": None}
    return {"scores": [str(val)], "upset": None}


def _parse_best_score(val):
    """Parse best_score from DB. New format is JSON array, old format is plain string."""
    return _parse_best_score_payload(val)["scores"]


def _parse_upset_score(val):
    upset = _parse_best_score_payload(val)["upset"]
    return upset if upset and upset != "?" else None


def _normalized_prediction_scores(
    pred: Prediction,
    *,
    crs: dict | None = None,
    odds_row: Odds | None = None,
    rank_a: int | None = None,
    rank_b: int | None = None,
) -> dict:
    """Return two likely + upset via the unified score pipeline."""
    hints = _parse_best_score(pred.best_score)
    upset_hint = _parse_upset_score(pred.best_score)
    dr = pred.draw_rate if pred.draw_rate is not None else max(
        0.0, 100.0 - (pred.win_rate or 0) - (pred.lose_rate or 0),
    )
    if crs:
        picks, upset = canonical_score_recommendations(
            crs,
            win_rate=pred.win_rate or 50.0,
            draw_rate=dr,
            lose_rate=pred.lose_rate or 50.0,
            model_scores=hints,
            sp_win=odds_row.win_win if odds_row else None,
            sp_draw=odds_row.draw if odds_row else None,
            sp_lose=odds_row.win_lose if odds_row else None,
            handicap=odds_row.handicap if odds_row else None,
            rank_a=rank_a,
            rank_b=rank_b,
        )
    else:
        picks, upset = hints[:2], upset_hint
    return normalize_score_prediction(picks, upset)


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
            ta = teams_by_key.get((match.competition_slug, match.team_a)) if match else None
            tb = teams_by_key.get((match.competition_slug, match.team_b)) if match else None
            norm = _normalized_prediction_scores(
                p,
                crs=crs,
                odds_row=odds_row,
                rank_a=ta.rank if ta else None,
                rank_b=tb.rank if tb else None,
            )
            result[p.match_id] = {
                **norm,
                "win_rate": p.win_rate,
                "draw_rate": p.draw_rate,
                "lose_rate": p.lose_rate,
                "confidence": p.confidence,
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
                result[mid] = {
                    **norm,
                    "win_rate": r.win_rate,
                    "draw_rate": r.draw_rate,
                    "lose_rate": r.lose_rate,
                    "confidence": 0.5,
                }
            else:
                r = rule_engine.evaluate(ta_dict, tb_dict, group_context=group_context)
                norm = normalize_score_prediction(
                    r.best_scores,
                    r.upset_score if r.upset_score != "?" else None,
                )
                result[mid] = {
                    **norm,
                    "win_rate": r.win_rate,
                    "draw_rate": r.draw_rate,
                    "lose_rate": r.lose_rate,
                    "confidence": 0.5,
                }

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
        actual_winner = "a" if match.result_a > match.result_b else ("b" if match.result_b > match.result_a else "draw")
        pred_winner = "a" if pred.win_rate > pred.lose_rate and pred.win_rate > pred.draw_rate else \
            ("b" if pred.lose_rate > pred.win_rate and pred.lose_rate > pred.draw_rate else "draw")

        if actual_winner == pred_winner:
            correct_results += 1

        # Score accuracy: actual in two likely picks or upset pick
        predicted_scores = list(_parse_best_score(pred.best_score))
        upset = _parse_upset_score(pred.best_score)
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
            return success(cached)

        # DB snapshot only for fused auto mode; single-model views must re-run LLM.
        if model_key == "auto":
            pred = (await db.execute(
                select(Prediction).where(Prediction.match_id == match_id).order_by(Prediction.create_time.desc()).limit(1)
            )).scalar_one_or_none()

            if pred:
                match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
                odds_row = (await db.execute(
                    select(Odds).where(Odds.match_id == match_id).order_by(Odds.id.desc()).limit(1)
                )).scalar_one_or_none()
                crs = None
                rank_a = rank_b = None
                if match and odds_row:
                    fused = prepare_fused_odds(odds_row, match.team_a, match.team_b)
                    crs = (fused or {}).get("score_odds")
                    ta = (await db.execute(
                        select(Team).where(Team.name == match.team_a, Team.competition_slug == match.competition_slug)
                    )).scalar_one_or_none()
                    tb = (await db.execute(
                        select(Team).where(Team.name == match.team_b, Team.competition_slug == match.competition_slug)
                    )).scalar_one_or_none()
                    rank_a = ta.rank if ta else None
                    rank_b = tb.rank if tb else None
                norm = _normalized_prediction_scores(
                    pred,
                    crs=crs,
                    odds_row=odds_row,
                    rank_a=rank_a,
                    rank_b=rank_b,
                )
                return success({
                    "match_id": match_id,
                    "team_a": match.team_a if match else "",
                    "team_b": match.team_b if match else "",
                    "stage": match.stage if match else "",
                    "win_rate": pred.win_rate,
                    "draw_rate": pred.draw_rate,
                    "lose_rate": pred.lose_rate,
                    **norm,
                    "handicap_result": pred.handicap_result,
                    "total_goals": pred.total_goals,
                    "reason": pred.reason,
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
