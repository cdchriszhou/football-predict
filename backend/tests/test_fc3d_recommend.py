"""Unit tests for 福彩3D normalization and shared digit recommend path."""

from service.fc3d_service import FC3D_GAME, _normalize_fc3d_row
from service.pailie_service import GAME_SPECS, _analyze_draws, _build_recommendations


def test_fc3d_in_catalog_specs():
    assert "fc3d" in GAME_SPECS
    assert GAME_SPECS["fc3d"]["alphabets"] == [10, 10, 10]
    assert FC3D_GAME["id"] == "fc3d"


def test_normalize_fc3d_row():
    raw = {
        "code": "2026190",
        "red": "8,6,5",
        "date": "2026-07-14",
        "poolmoney": "0",
        "sales": "49,221,224",
    }
    item = _normalize_fc3d_row(raw)
    assert item is not None
    assert item["issue"] == "2026190"
    assert item["digits"] == [8, 6, 5]
    assert item["result"] == "8 6 5"
    assert item["sale_amount"] == 49221224.0


def test_normalize_fc3d_compact():
    item = _normalize_fc3d_row({"code": "1", "red": "702", "date": "2026-01-01"})
    assert item is not None
    assert item["digits"] == [7, 0, 2]


def test_normalize_fc3d_rejects_bad():
    assert _normalize_fc3d_row({"code": "1", "red": "1,2"}) is None
    assert _normalize_fc3d_row({"red": "1,2,3"}) is None


def test_fc3d_analyze_includes_unseen_digits():
    """字母表内从未出现的号码仍参与评分（冷号 miss=样本长度）。"""
    draws = [
        {"issue": str(i), "digits": [1, 2, 3], "result": "1 2 3"}
        for i in range(30)
    ]
    analysis = _analyze_draws(draws, [10, 10, 10])
    # 百位 digit 0 从未出现，仍应有统计行
    hundreds = {r["digit"]: r for r in analysis["position_stats"][0]}
    assert 0 in hundreds
    assert hundreds[0]["count"] == 0
    assert hundreds[0]["miss"] == 30
    assert hundreds[0]["score"] >= 0

    recs = _build_recommendations("fc3d", draws, analysis)
    assert len(recs) == 5
    for r in recs:
        assert len(r["digits"]) == 3
        assert all(0 <= d <= 9 for d in r["digits"])
