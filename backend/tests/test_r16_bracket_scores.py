"""1/8 bracket must resolve scores and feeders for completed fixtures."""
from data.knockout_advance import build_slot_index, match_winner, resolve_fixture_teams
from data.match_status import confirmed_scores_from_history
from data.worldcup_history import HISTORICAL_MATCHES
from types import SimpleNamespace


def _slot(no, ta, tb, ra=None, rb=None):
    return SimpleNamespace(
        id=no,
        competition_slug="worldcup-2026",
        stage="1/8决赛",
        team_a=ta,
        team_b=tb,
        match_time=__import__("datetime").datetime(2026, 7, 5, 5, 0),
        result_a=ra,
        result_b=rb,
        penalty_a=None,
        penalty_b=None,
    )


def test_july5_paraguay_france_history():
    row = next(
        m for m in HISTORICAL_MATCHES
        if m.get("year") == 2026 and m.get("team_a") == "巴拉圭" and m.get("team_b") == "法国"
    )
    assert row["result_a"] == 0 and row["result_b"] == 1


def test_match_winner_with_placeholder_and_history():
    by_no = {
        77: _slot(77, "法国", "瑞典", 3, 0),
        89: _slot(89, "巴拉圭", "第77场胜者", None, None),
    }
    w = match_winner(by_no[89], match_no=89, by_no=by_no)
    assert w == "法国"


def test_build_slot_index_from_api_dicts():
    """API match_to_dict rows (ISO kickoff) must still map to FIFA slots."""
    from api.matches import match_to_dict
    from types import SimpleNamespace

    def row(no, stage, ta, tb, ra, rb, mt):
        m = SimpleNamespace(
            id=no,
            competition_slug="worldcup-2026",
            stage=stage,
            group_name="",
            team_a=ta,
            team_b=tb,
            match_time=mt,
            location="",
            stadium="",
            result_a=ra,
            result_b=rb,
            penalty_a=None,
            penalty_b=None,
            status="finished",
            season=None,
            matchday=None,
        )
        return m

    from datetime import datetime
    r16 = [
        row(77, "1/16决赛", "法国", "瑞典", 3, 0, datetime(2026, 7, 1, 6, 0)),
        row(74, "1/16决赛", "德国", "巴拉圭", 1, 1, datetime(2026, 6, 30, 4, 30)),
    ]
    r8 = [
        row(89, "1/8决赛", "巴拉圭", "法国", 0, 1, datetime(2026, 7, 5, 5, 0)),
        row(90, "1/8决赛", "加拿大", "摩洛哥", 0, 3, datetime(2026, 7, 5, 0, 0)),
    ]
    ko = build_slot_index({"1/16决赛": r16, "1/8决赛": r8})
    dict_rows = {
        "1/16决赛": [match_to_dict(m, knockout_by_no=ko) for m in r16],
        "1/8决赛": [match_to_dict(m, knockout_by_no=ko) for m in r8],
    }
    idx = build_slot_index(dict_rows)
    m89 = idx.get(89)
    assert m89 is not None
    assert m89.get("result_a") == 0 and m89.get("result_b") == 1
    m90 = idx.get(90)
    assert m90 is not None
    assert m90.get("result_a") == 0 and m90.get("result_b") == 3


def test_quarter_feeder_from_finished_r16():
    by_no = {
        77: _slot(77, "法国", "瑞典", 3, 0),
        89: _slot(89, "巴拉圭", "第77场胜者", None, None),
        90: _slot(90, "加拿大", "摩洛哥", 0, 3),
    }
    ta, tb = resolve_fixture_teams(97, by_no)
    assert ta == "法国"
    assert tb == "摩洛哥"
