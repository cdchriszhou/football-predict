"""Normalize match score predictions: two likely scorelines + one upset."""
from __future__ import annotations

import json

LIKELY_SCORE_COUNT = 2

# Sporttery CRS settles on regulation time (90 min); ET / penalty goals excluded.
SPORTTERY_SCORE_NOTE = "比分预测为常规时间（90分钟）赛果，体彩 CRS 不含加时及点球进球。"


def sporttery_actual_score(
    *,
    result_a: int,
    result_b: int,
    regulation_a: int | None = None,
    regulation_b: int | None = None,
    extra_time: bool = False,
    reversed_teams: bool = False,
) -> str:
    """Actual score for CRS / sporttery settlement (regulation time only)."""
    if extra_time and regulation_a is not None and regulation_b is not None:
        ra, rb = int(regulation_a), int(regulation_b)
    else:
        ra, rb = int(result_a), int(result_b)
    if reversed_teams:
        ra, rb = rb, ra
    return f"{ra}:{rb}"


def actual_score_from_history(
    hist: dict,
    *,
    team_a: str | None = None,
    team_b: str | None = None,
) -> str | None:
    """Regulation-time actual from a worldcup_history row (sporttery口径)."""
    if hist.get("result_a") is None or hist.get("result_b") is None:
        return None
    reversed_teams = False
    if team_a and team_b:
        ta, tb = hist.get("team_a"), hist.get("team_b")
        if ta == team_b and tb == team_a:
            reversed_teams = True
    return sporttery_actual_score(
        result_a=int(hist["result_a"]),
        result_b=int(hist["result_b"]),
        regulation_a=hist.get("regulation_a"),
        regulation_b=hist.get("regulation_b"),
        extra_time=bool(hist.get("extra_time")),
        reversed_teams=reversed_teams,
    )


def actual_score_for_match(
    *,
    result_a: int,
    result_b: int,
    team_a: str,
    team_b: str,
    hist: dict | None = None,
) -> str:
    """Best available sporttery actual: history regulation overlay, else DB full-time."""
    if hist:
        from_hist = actual_score_from_history(hist, team_a=team_a, team_b=team_b)
        if from_hist:
            return from_hist
    return f"{int(result_a)}:{int(result_b)}"


def parse_best_score_payload(val) -> dict:
    """Parse best_score DB field — array, object, or legacy string."""
    empty = {"scores": [], "upset": None}
    if val is None:
        return empty
    if isinstance(val, dict):
        scores = val.get("scores") or val.get("likely") or val.get("best_scores")
        if isinstance(scores, str):
            scores = [scores]
        upset = val.get("upset") or val.get("upset_score")
        return {"scores": list(scores or []), "upset": upset}
    if isinstance(val, list):
        return {"scores": [s for s in val if s], "upset": None}
    if isinstance(val, str):
        if val.startswith("{") or val.startswith("["):
            try:
                return parse_best_score_payload(json.loads(val))
            except json.JSONDecodeError:
                pass
        return {"scores": [val] if val and val != "?" else [], "upset": None}
    return empty


def reconcile_prediction_view(
    scores: list | None,
    upset: str | None,
    win_rate: float,
    draw_rate: float,
    lose_rate: float,
) -> dict:
    """Normalize score picks and align W/D/L with the primary scoreline."""
    from service.score_pick import align_wdl_to_score_picks, reconcile_wdl_with_score_picks

    norm = normalize_score_prediction(scores, upset)
    wr, dr, lr = reconcile_wdl_with_score_picks(
        norm["best_scores"], win_rate, draw_rate, lose_rate,
    )
    wr, dr, lr = align_wdl_to_score_picks(norm["best_scores"], wr, dr, lr)
    return {**norm, "win_rate": wr, "draw_rate": dr, "lose_rate": lr}


def normalize_score_prediction(
    scores: list | None,
    upset: str | None = None,
) -> dict:
    """Return exactly two likely scorelines and optional one upset scoreline."""
    upset_val = upset if upset and upset != "?" else None
    skip = {upset_val} if upset_val else set()

    likely: list[str] = []
    for s in scores or []:
        if not s or s == "?" or s in skip or s in likely:
            continue
        likely.append(s)
        if len(likely) >= LIKELY_SCORE_COUNT:
            break

    return {
        "best_scores": likely,
        "best_score": likely[0] if likely else "?",
        "upset_score": upset_val,
    }
