"""Unit tests for pailie frequency recommendations (no network)."""

from service.pailie_service import _analyze_draws, _build_recommendations, _pick_direct_numbers


def _mk_draws(rows: list[list[int]]):
    return [
        {"issue": str(i), "digits": nums, "result": " ".join(map(str, nums))}
        for i, nums in enumerate(rows)
    ]


def test_analyze_prefers_frequent_digit_on_position():
    # Hundreds mostly 7, tens 2, ones 9
    draws = _mk_draws([[7, 2, 9]] * 20 + [[1, 0, 3]] * 2)
    analysis = _analyze_draws(draws, 3)
    top_hundreds = analysis["position_stats"][0][0]["digit"]
    assert top_hundreds == 7
    assert analysis["sample_size"] == 22
    assert 7 in analysis["hot_digits"]


def test_pick_direct_and_build_recs():
    draws = _mk_draws([[5, 5, 1], [5, 4, 1], [5, 3, 1], [2, 2, 8], [2, 7, 8]] * 4)
    analysis = _analyze_draws(draws, 3)
    picks = _pick_direct_numbers(analysis["position_scores"], count=3)
    assert len(picks) >= 1
    assert all(len(p) == 3 for p in picks)
    recs = _build_recommendations("pl3", draws, analysis)
    assert any(r["mode"] == "direct" for r in recs)
    assert any(r["id"] == "direct-1" for r in recs)
    modes = {r["mode"] for r in recs}
    assert "group3" in modes or "group6" in modes
