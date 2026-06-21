"""Normalize match score predictions: two likely scorelines + one upset."""
from __future__ import annotations

import json

LIKELY_SCORE_COUNT = 2


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
