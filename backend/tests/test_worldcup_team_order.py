"""FIFA official home/away order must match schedule generator and venues."""
from crawler.schedule_crawler import _build_expected_matches
from data.worldcup_venues import FIFA_GROUP_VENUES, canonical_team_order


def test_all_group_matches_use_fifa_team_order():
    expected = _build_expected_matches()
    assert len(expected) == 72
    for item in expected:
        ta, tb = item["team_a"], item["team_b"]
        assert (ta, tb) in FIFA_GROUP_VENUES, f"Missing venue key: {ta} vs {tb}"
        ca, cb = canonical_team_order(ta, tb)
        assert (ta, tb) == (ca, cb)


def test_round2_examples_home_away():
    expected = {(m["team_a"], m["team_b"]) for m in _build_expected_matches()}
    assert ("乌拉圭", "佛得角") in expected
    assert ("新西兰", "埃及") in expected
    assert ("佛得角", "乌拉圭") not in expected
    assert ("埃及", "新西兰") not in expected


def test_canonical_team_order_swaps_when_needed():
    assert canonical_team_order("佛得角", "乌拉圭") == ("乌拉圭", "佛得角")
    assert canonical_team_order("埃及", "新西兰") == ("新西兰", "埃及")
    assert canonical_team_order("西班牙", "佛得角") == ("西班牙", "佛得角")
