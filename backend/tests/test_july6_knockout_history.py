"""Confirmed July 6 R16 fixtures must exist in history for placeholder DB rows."""
from data.worldcup_history import HISTORICAL_MATCHES


def _wc2026_key(team_a: str, team_b: str, stage: str) -> dict | None:
    for item in HISTORICAL_MATCHES:
        if item.get("year") != 2026:
            continue
        if item.get("team_a") == team_a and item.get("team_b") == team_b and item.get("stage") == stage:
            return item
    return None


def test_july6_r16_brazil_norway():
    row = _wc2026_key("巴西", "挪威", "1/8决赛")
    assert row is not None
    assert row["result_a"] == 1 and row["result_b"] == 2
    assert row.get("match_time")


def test_july6_r16_mexico_england():
    row = _wc2026_key("墨西哥", "英格兰", "1/8决赛")
    assert row is not None
    assert row["result_a"] == 1 and row["result_b"] == 2
    assert row.get("match_time")


def test_july1_r32_feeders_for_july6():
    for ta, tb, winner_side in (
        ("科特迪瓦", "挪威", "b"),
        ("墨西哥", "厄瓜多尔", "a"),
        ("英格兰", "刚果(金)", "a"),
    ):
        row = _wc2026_key(ta, tb, "1/16决赛")
        assert row is not None, f"missing R32 {ta} vs {tb}"
        ra, rb = row["result_a"], row["result_b"]
        assert ra is not None and rb is not None
        if winner_side == "a":
            assert ra > rb
        else:
            assert rb > ra
