"""Normalize match score predictions: two likely scorelines + one upset."""
from __future__ import annotations

LIKELY_SCORE_COUNT = 2


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
