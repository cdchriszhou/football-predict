"""Unit tests for SSQ (双色球) frequency recommendations (no network)."""

from service.ssq_service import (
    _normalize_ssq_row,
    _validate_ssq_ai,
    analyze_ssq,
    build_ssq_recommendations,
)


def test_normalize_ssq_row():
    raw = {
        "code": "2026075",
        "red": "01,05,12,18,23,30",
        "blue": "08",
        "date": "2026-07-14",
        "poolmoney": "1,234,567,890.50",
        "sales": "350,000,000",
    }
    item = _normalize_ssq_row(raw)
    assert item is not None
    assert item["issue"] == "2026075"
    assert item["red"] == [1, 5, 12, 18, 23, 30]
    assert item["blue"] == 8
    assert item["digits"] == [1, 5, 12, 18, 23, 30, 8]
    assert "+" in item["result"]
    assert item["pool_balance"] == 1234567890.50


def test_normalize_ssq_rejects_bad_red():
    assert _normalize_ssq_row({"code": "1", "red": "01,02,03", "blue": "08"}) is None
    assert _normalize_ssq_row({"code": "1", "red": "01,05,12,18,23,30", "blue": "99"}) is None


def test_analyze_and_build_ssq_recs():
    draws = []
    for i in range(40):
        reds = sorted({((i + k * 3) % 33) + 1 for k in range(6)})
        while len(reds) < 6:
            reds.append(((len(reds) * 7 + i) % 33) + 1)
            reds = sorted(set(reds))
        reds = reds[:6]
        blue = (i % 16) + 1
        draws.append({
            "issue": str(i),
            "red": reds,
            "blue": blue,
            "digits": reds + [blue],
            "result": " ".join(f"{x:02d}" for x in reds) + f" + {blue:02d}",
        })

    analysis = analyze_ssq(draws)
    assert analysis["sample_size"] == 40
    assert len(analysis["red_stats"]) == 33
    assert len(analysis["blue_stats"]) == 16
    assert len(analysis["position_stats"]) == 2
    assert len(analysis["hot_digits"]) == 6

    recs = build_ssq_recommendations(analysis)
    assert len(recs) == 5
    for r in recs:
        assert r["mode"] == "ssq"
        assert len(r["digits"]) == 7
        assert len(set(r["digits"][:6])) == 6
        assert all(1 <= n <= 33 for n in r["digits"][:6])
        assert 1 <= r["digits"][6] <= 16
        assert r["bets"] == 1


def test_validate_ssq_ai():
    assert _validate_ssq_ai({"red": [1, 2, 3, 4, 5, 6], "blue": 8}) == ([1, 2, 3, 4, 5, 6], 8)
    assert _validate_ssq_ai({"digits": [10, 11, 12, 13, 14, 15, 3]}) == ([10, 11, 12, 13, 14, 15], 3)
    assert _validate_ssq_ai({"red": [1, 2, 3], "blue": 8}) is None
    assert _validate_ssq_ai({"red": [1, 2, 3, 4, 5, 6], "blue": 99}) is None
