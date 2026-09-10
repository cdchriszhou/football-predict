"""Unit tests for SSQ (双色球) frequency recommendations (no network)."""

from service.ssq_service import (
    _BLUE_LOW_MAX,
    _SUM_EXTREME_HI,
    _SUM_EXTREME_LO,
    _fit_reds_to_sum,
    _normalize_ssq_row,
    _validate_ssq_ai,
    analyze_ssq,
    build_ssq_dantuo,
    build_ssq_fushi,
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


def _make_draws(n: int = 40) -> list[dict]:
    draws = []
    for i in range(n):
        reds = sorted({((i + k * 3) % 33) + 1 for k in range(6)})
        while len(reds) < 6:
            reds.append(((len(reds) * 7 + i) % 33) + 1)
            reds = sorted(set(reds))
        reds = reds[:6]
        # Bias blues into 01-10 like real history
        blue = (i % 10) + 1
        draws.append({
            "issue": str(i),
            "red": reds,
            "blue": blue,
            "digits": reds + [blue],
            "result": " ".join(f"{x:02d}" for x in reds) + f" + {blue:02d}",
        })
    return draws


def test_analyze_and_build_ssq_recs():
    analysis = analyze_ssq(_make_draws())
    assert analysis["sample_size"] == 40
    assert len(analysis["red_stats"]) == 33
    assert len(analysis["blue_stats"]) == 16
    assert len(analysis["position_stats"]) == 2
    assert len(analysis["hot_digits"]) == 6
    assert "sum_stats" in analysis
    assert analysis["sum_stats"]["target_lo"] <= analysis["sum_stats"]["target_hi"]
    assert analysis["blue_zone"]["low_max"] == _BLUE_LOW_MAX
    assert analysis["blue_zone"]["low_rate"] >= 0.9

    # 01-10 blues should outrank after zone boost on average
    low_avg = sum(analysis["blue_score_map"][n] for n in range(1, 11)) / 10
    high_avg = sum(analysis["blue_score_map"][n] for n in range(11, 17)) / 6
    assert low_avg >= high_avg

    recs = build_ssq_recommendations(analysis)
    assert len(recs) == 5
    singles = [r for r in recs if r["mode"] == "ssq"]
    fushi = [r for r in recs if r["mode"] == "fushi"]
    dantuo = [r for r in recs if r["mode"] == "dantuo"]
    assert len(singles) == 3
    assert len(fushi) == 1
    assert len(dantuo) == 1
    for r in singles:
        assert len(r["digits"]) == 7
        assert len(set(r["digits"][:6])) == 6
        assert all(1 <= n <= 33 for n in r["digits"][:6])
        assert 1 <= r["digits"][6] <= 16
        assert r["bets"] == 1
        # 仅避免极端和值；不再强制挤进窄历史分位带
        assert _SUM_EXTREME_LO - 5 <= r["red_sum"] <= _SUM_EXTREME_HI + 5
        # Singles diversify blues across the package
        blues = [r["blue"] for r in singles]
        assert len(set(blues)) == len(blues)  # 互异
        assert all(1 <= b <= 16 for b in blues)
        assert sum(1 for b in blues if b > _BLUE_LOW_MAX) <= 1


def test_build_ssq_dantuo():
    analysis = analyze_ssq(_make_draws())
    dt = build_ssq_dantuo(analysis, seed=1)
    assert dt["mode"] == "dantuo"
    assert len(dt["dan"]) == 2
    assert len(dt["tuo"]) == 5
    assert not set(dt["dan"]) & set(dt["tuo"])
    assert dt["blue_pool"] == [dt["blue"]]
    assert 1 <= dt["blue"] <= 16
    assert dt["bets"] == 5  # C(5,4)
    assert dt["amount"] == 10


def test_build_ssq_fushi():
    analysis = analyze_ssq(_make_draws())
    fs = build_ssq_fushi(analysis, seed=2)
    assert fs["mode"] == "fushi"
    assert len(fs["red"]) == 7
    assert len(set(fs["red"])) == 7
    assert all(1 <= n <= 33 for n in fs["red"])
    assert 1 <= fs["blue"] <= 16
    assert fs["bets"] == 7
    assert fs["amount"] == 14


def test_ssq_singles_red_overlap_capped():
    """单式之间红球重叠应 <4，避免滑窗造成五注近似同一注。"""
    analysis = analyze_ssq(_make_draws())
    recs = build_ssq_recommendations(analysis, seed=0)
    singles = [r for r in recs if r["mode"] == "ssq"]
    sets = [set(r["red"]) for r in singles]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert len(sets[i] & sets[j]) < 4, (i, j, sorted(sets[i] & sets[j]))


def test_ssq_recs_include_high_blue_diversity():
    from service.ssq_service import _pick_ssq_sets

    analysis = analyze_ssq(_make_draws())
    recs = build_ssq_recommendations(analysis, seed=0)
    singles = [r for r in recs if r["mode"] == "ssq"]
    blues = [r["blue"] for r in singles]
    assert len(blues) == len(set(blues)), blues
    five = _pick_ssq_sets(analysis, count=5, seed=0)
    assert any(b > _BLUE_LOW_MAX for _, b in five)



def test_fit_reds_to_sum_pulls_into_band():
    fitted = _fit_reds_to_sum([1, 2, 3, 4, 5, 6], list(range(1, 34)), lo=90, hi=120, target=102)
    assert len(fitted) == 6
    assert 90 <= sum(fitted) <= 120


def test_validate_ssq_ai():
    assert _validate_ssq_ai({"red": [1, 2, 3, 4, 5, 6], "blue": 8}) == ([1, 2, 3, 4, 5, 6], 8)
    assert _validate_ssq_ai({"digits": [10, 11, 12, 13, 14, 15, 3]}) == ([10, 11, 12, 13, 14, 15], 3)
    assert _validate_ssq_ai({"red": [1, 2, 3], "blue": 8}) is None
    assert _validate_ssq_ai({"red": [1, 2, 3, 4, 5, 6], "blue": 99}) is None
