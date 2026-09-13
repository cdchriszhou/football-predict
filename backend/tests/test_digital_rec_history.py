"""数字彩推荐持久化与开奖对照（含复式/胆拖）。"""

from __future__ import annotations

from service.digital_rec_store import _normalize_picks, _pick_from_rec
from service.pailie_service import _prediction_hits, _prediction_payload


def test_pick_from_rec_fushi_uses_full_seven_reds():
    rec = {
        "mode": "fushi",
        "red": [1, 2, 3, 4, 5, 6, 7],
        "blue": 9,
        "digits": [1, 2, 3, 4, 5, 6, 9],  # 样例单式，不应覆盖完整复式
        "display": "复式红 01 02 03 04 05 06 07 + 蓝 09",
        "bets": 7,
        "amount": 14,
        "label": "复式参考",
    }
    pick = _pick_from_rec(rec)
    assert pick is not None
    assert pick["mode"] == "fushi"
    assert pick["red"] == [1, 2, 3, 4, 5, 6, 7]
    assert pick["blue"] == 9
    assert pick["digits"] == [1, 2, 3, 4, 5, 6, 7, 9]
    assert pick["bets"] == 7


def test_pick_from_rec_dantuo_concatenates_dan_tuo_blue():
    rec = {
        "mode": "dantuo",
        "dan": [3, 18],
        "tuo": [5, 9, 12, 21, 30],
        "blue": 8,
        "digits": [3, 18, 5, 9, 12, 21, 8],
        "display": "胆 03 18 | 拖 05 09 12 21 30 | 蓝 08",
        "label": "胆拖参考",
    }
    pick = _pick_from_rec(rec)
    assert pick is not None
    assert pick["mode"] == "dantuo"
    assert pick["dan"] == [3, 18]
    assert pick["tuo"] == [5, 9, 12, 21, 30]
    assert pick["digits"] == [3, 18, 5, 9, 12, 21, 30, 8]


def test_normalize_picks_keeps_compound_modes():
    recs = [
        {"mode": "ssq", "digits": [1, 2, 3, 4, 5, 6, 7], "display": "a"},
        {"mode": "ssq", "digits": [2, 3, 4, 5, 6, 7, 8], "display": "b"},
        {"mode": "ssq", "digits": [3, 4, 5, 6, 7, 8, 9], "display": "c"},
        {
            "mode": "fushi",
            "red": [1, 2, 3, 4, 5, 6, 7],
            "blue": 10,
            "digits": [1, 2, 3, 4, 5, 6, 10],
            "display": "f",
        },
        {
            "mode": "dantuo",
            "dan": [1, 11],
            "tuo": [2, 3, 4, 5, 6],
            "blue": 12,
            "digits": [1, 11, 2, 3, 4, 5, 12],
            "display": "d",
        },
    ]
    picks = _normalize_picks(recs)
    assert len(picks) == 5
    assert [p.get("mode") for p in picks] == ["ssq", "ssq", "ssq", "fushi", "dantuo"]


def test_ssq_fushi_hits_mark_each_of_seven_reds():
    # 开奖 01 02 03 04 05 06 + 16；复式含 01-07 + 蓝 16
    actual = [1, 2, 3, 4, 5, 6, 16]
    pred = [1, 2, 3, 4, 5, 6, 7, 16]
    hits = _prediction_hits("ssq", pred, actual, mode="fushi")
    assert hits == [True, True, True, True, True, True, False, True]


def test_ssq_dantuo_hits_align_with_dan_tuo_blue():
    actual = [3, 8, 12, 18, 21, 30, 8]
    # 胆 03 18 | 拖 05 09 12 21 30 | 蓝 08
    pred = [3, 18, 5, 9, 12, 21, 30, 8]
    hits = _prediction_hits("ssq", pred, actual, mode="dantuo")
    assert hits == [True, True, False, False, True, True, True, True]


def test_prediction_payload_includes_compound_fields():
    pick = {
        "mode": "fushi",
        "red": [1, 2, 3, 4, 5, 6, 7],
        "blue": 9,
        "digits": [1, 2, 3, 4, 5, 6, 7, 9],
        "display": "复式",
        "label": "复式参考",
        "bets": 7,
        "amount": 14,
        "source": "frequency",
    }
    payload = _prediction_payload(pick, [1, 2, 3, 4, 5, 8, 9], "ssq")
    assert payload is not None
    assert payload["mode"] == "fushi"
    assert payload["red"] == [1, 2, 3, 4, 5, 6, 7]
    assert payload["blue"] == 9
    assert payload["bets"] == 7
    assert len(payload["hits"]) == 8
    assert payload["hits"][-1] is True
