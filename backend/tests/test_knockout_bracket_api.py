"""Knockout bracket fixture seeding."""
from data.knockout_advance import KNOCKOUT_STAGES


def test_knockout_stages_cover_bracket():
    assert "1/16决赛" in KNOCKOUT_STAGES
    assert "决赛" in KNOCKOUT_STAGES
    assert len(KNOCKOUT_STAGES) == 6
