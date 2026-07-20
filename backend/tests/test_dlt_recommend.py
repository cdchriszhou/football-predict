"""Unit tests for DLT (大乐透) frequency recommendations (no network)."""

from service.dlt_service import (
    _normalize_dlt_row,
    _validate_dlt_ai,
    analyze_dlt,
    build_dlt_recommendations,
)


def test_normalize_dlt_row():
    raw = {
        "lotteryDrawNum": "26080",
        "lotteryDrawResult": "05 10 15 21 23 07 08",
        "lotteryDrawTime": "2026-07-18",
        "poolBalanceAfterdraw": "765,513,154.43",
        "totalSaleAmount": "350,000,000",
    }
    item = _normalize_dlt_row(raw)
    assert item is not None
    assert item["front"] == [5, 10, 15, 21, 23]
    assert item["back"] == [7, 8]
    assert item["digits"] == [5, 10, 15, 21, 23, 7, 8]
    assert "+" in item["result"]
    assert item["pool_balance"] == 765513154.43


def test_normalize_dlt_rejects_bad():
    assert _normalize_dlt_row({"lotteryDrawNum": "1", "lotteryDrawResult": "01 02 03"}) is None
    assert _normalize_dlt_row({
        "lotteryDrawNum": "1",
        "lotteryDrawResult": "01 02 03 04 05 99 08",
    }) is None


def test_analyze_and_build_dlt_recs():
    draws = []
    for i in range(40):
        fronts = sorted({((i + k * 4) % 35) + 1 for k in range(5)})
        while len(fronts) < 5:
            fronts.append(((len(fronts) * 5 + i) % 35) + 1)
            fronts = sorted(set(fronts))
        fronts = fronts[:5]
        backs = sorted({((i + k) % 12) + 1 for k in range(2)})
        while len(backs) < 2:
            backs.append(((len(backs) * 3 + i) % 12) + 1)
            backs = sorted(set(backs))
        backs = backs[:2]
        draws.append({
            "issue": str(i),
            "front": fronts,
            "back": backs,
            "digits": fronts + backs,
            "result": " ".join(f"{x:02d}" for x in fronts) + " + " + " ".join(f"{x:02d}" for x in backs),
        })

    analysis = analyze_dlt(draws)
    assert analysis["sample_size"] == 40
    assert len(analysis["front_stats"]) == 35
    assert len(analysis["back_stats"]) == 12
    assert len(analysis["position_stats"]) == 2

    recs = build_dlt_recommendations(analysis)
    assert len(recs) == 5
    for r in recs:
        assert r["mode"] == "dlt"
        assert len(r["digits"]) == 7
        assert len(set(r["digits"][:5])) == 5
        assert len(set(r["digits"][5:])) == 2
        assert all(1 <= n <= 35 for n in r["digits"][:5])
        assert all(1 <= n <= 12 for n in r["digits"][5:])


def test_validate_dlt_ai():
    assert _validate_dlt_ai({"front": [1, 2, 3, 4, 5], "back": [6, 7]}) == ([1, 2, 3, 4, 5], [6, 7])
    assert _validate_dlt_ai({"digits": [10, 11, 12, 13, 14, 3, 8]}) == ([10, 11, 12, 13, 14], [3, 8])
    assert _validate_dlt_ai({"front": [1, 2, 3], "back": [6, 7]}) is None
    assert _validate_dlt_ai({"front": [1, 2, 3, 4, 5], "back": [6, 99]}) is None
