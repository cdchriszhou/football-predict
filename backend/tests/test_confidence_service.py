"""Confidence should vary by match context — not flat 88%."""
from service.confidence_service import compute_score_confidence, compute_wdl_confidence


def test_score_confidence_not_flat_at_cap():
    analysis_like = {
        "confidence_penalty": 0.05,
        "alerts": [],
    }
    strong_fav = compute_score_confidence(
        scoreline="2:0",
        rank=0,
        model_scores=["2:0", "1:0", "3:0"],
        crs_odd=5.5,
        blend={"win": 62.0, "draw": 22.0, "lose": 16.0},
        confidence_penalty=analysis_like["confidence_penalty"],
        ai_confidence=0.82,
        teams_available=True,
        matchday=1,
    )
    tight = compute_score_confidence(
        scoreline="1:1",
        rank=0,
        model_scores=["1:1", "0:0", "1:0"],
        crs_odd=8.0,
        blend={"win": 36.0, "draw": 34.0, "lose": 30.0},
        confidence_penalty=0.12,
        ai_confidence=0.75,
        teams_available=True,
        matchday=2,
        alerts=["模型与市场存在分歧"],
    )
    upset = compute_score_confidence(
        scoreline="0:1",
        rank=0,
        model_scores=["2:0", "1:0"],
        crs_odd=12.0,
        blend={"win": 55.0, "draw": 25.0, "lose": 20.0},
        is_upset=True,
        matchday=2,
    )
    assert strong_fav != 0.88
    assert strong_fav > tight
    assert strong_fav > upset
    assert tight <= 0.74
    assert upset <= 0.52


def test_wdl_confidence_varies_by_agreement():
    clear = compute_wdl_confidence(
        pick_code="win",
        blend_pct=58.0,
        model_agreements=3,
        ai_confidence=0.85,
        teams_available=True,
        blend={"win": 58.0, "draw": 24.0, "lose": 18.0},
    )
    uncertain = compute_wdl_confidence(
        pick_code="draw",
        blend_pct=36.0,
        model_agreements=0,
        ai_confidence=0.72,
        confidence_penalty=0.10,
        alerts=["冷门风险偏高"],
        blend={"win": 35.0, "draw": 36.0, "lose": 29.0},
        matchday=2,
    )
    assert clear > uncertain
    assert clear <= 0.86
    assert uncertain >= 0.38
