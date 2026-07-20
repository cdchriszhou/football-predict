"""Unit tests for digital lottery frequency recommendations (no network)."""

from service.pailie_service import (
    GAME_SPECS,
    _analyze_draws,
    _build_recommendations,
    _normalize_draw_row,
    _pick_direct_numbers,
    _validate_ai_digits,
)


def _mk_draws(rows: list[list[int]]):
    return [
        {"issue": str(i), "digits": nums, "result": " ".join(map(str, nums))}
        for i, nums in enumerate(rows)
    ]


def test_analyze_prefers_frequent_digit_on_position():
    draws = _mk_draws([[7, 2, 9]] * 20 + [[1, 0, 3]] * 2)
    analysis = _analyze_draws(draws, [10, 10, 10])
    top_hundreds = analysis["position_stats"][0][0]["digit"]
    assert top_hundreds == 7
    assert analysis["sample_size"] == 22
    assert 7 in analysis["hot_digits"]


def test_pick_direct_and_build_recs_pl3():
    draws = _mk_draws([[5, 5, 1], [5, 4, 1], [5, 3, 1], [2, 2, 8], [2, 7, 8]] * 4)
    analysis = _analyze_draws(draws, [10, 10, 10])
    picks = _pick_direct_numbers(analysis["position_scores"], [10, 10, 10], count=3)
    assert len(picks) >= 1
    assert all(len(p) == 3 for p in picks)
    recs = _build_recommendations("pl3", draws, analysis)
    assert len(recs) == 5
    assert all(r["mode"] == "direct" for r in recs)
    assert all(r["id"].startswith("pick-") for r in recs)


def test_qxc_normalize_and_analyze():
    raw = {
        "lotteryDrawNum": "26080",
        "lotteryDrawResult": "1 2 3 4 5 6 14",
        "lotteryDrawTime": "2026-07-18",
    }
    item = _normalize_draw_row(raw, "qxc")
    assert item is not None
    assert item["digits"] == [1, 2, 3, 4, 5, 6, 14]

    draws = _mk_draws([[1, 2, 3, 4, 5, 6, 14]] * 15 + [[9, 8, 7, 6, 5, 4, 0]] * 5)
    alphabets = GAME_SPECS["qxc"]["alphabets"]
    analysis = _analyze_draws(draws, alphabets)
    assert len(analysis["position_scores"]) == 7
    assert len(analysis["position_scores"][6]) == 15
    recs = _build_recommendations("qxc", draws, analysis)
    assert len(recs) == 5
    assert all(len(r["digits"]) == 7 for r in recs)
    assert all(0 <= r["digits"][6] <= 14 for r in recs)


def test_parse_money_and_pool_fields():
    from service.pailie_service import _parse_money

    assert _parse_money("174,321,661.80") == 174321661.80
    assert _parse_money("0") == 0.0
    raw = {
        "lotteryDrawNum": "23154",
        "lotteryDrawResult": "4 3 3 5 0",
        "lotteryDrawTime": "2023-06-13",
        "poolBalanceAfterdraw": "174,321,661.80",
        "totalSaleAmount": "20,526,970",
        "prizeLevelList": [
            {"prizeLevel": "一等奖", "stakeAmount": "100,000", "stakeCount": "52", "totalPrizeAmount": "5,200,000"},
        ],
    }
    item = _normalize_draw_row(raw, "pl5")
    assert item["pool_balance"] == 174321661.80
    assert item["pool_balance_text"] == "174,321,661.80"
    assert item["sale_amount"] == 20526970.0
    assert item["prize_levels"][0]["level"] == "一等奖"
    assert item["has_floating_pool"] is True


def test_validate_ai_digits_qxc():
    alphabets = GAME_SPECS["qxc"]["alphabets"]
    assert _validate_ai_digits([1, 2, 3, 4, 5, 6, 14], alphabets) == [1, 2, 3, 4, 5, 6, 14]
    assert _validate_ai_digits([1, 2, 3, 4, 5, 6, 15], alphabets) is None
    assert _validate_ai_digits([1, 2, 3], alphabets) is None
