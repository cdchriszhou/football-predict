"""2026/27 league roster and seed-fixture policy."""
from data.league_seed import LEAGUE_TEAMS, ensure_league_data
from data.club_name_map import resolve_club_cn


def test_big_five_roster_sizes():
    assert len(LEAGUE_TEAMS["premier-league"]) == 20
    assert len(LEAGUE_TEAMS["la-liga"]) == 20
    assert len(LEAGUE_TEAMS["serie-a"]) == 20
    assert len(LEAGUE_TEAMS["bundesliga"]) == 18
    assert len(LEAGUE_TEAMS["ligue-1"]) == 18


def test_premier_league_2026_27_promotions():
    names = {cn for cn, _en, _r in LEAGUE_TEAMS["premier-league"]}
    assert {"考文垂", "赫尔城", "伊普斯维奇", "利兹联", "桑德兰"} <= names
    assert "西汉姆联" not in names
    assert "狼队" not in names
    assert "莱斯特城" not in names


def test_la_liga_2026_27_promotions():
    names = {cn for cn, _en, _r in LEAGUE_TEAMS["la-liga"]}
    assert {"桑坦德竞技", "拉科鲁尼亚", "马拉加"} <= names
    assert "赫罗纳" not in names
    assert "马洛卡" not in names


def test_name_map_new_clubs():
    assert resolve_club_cn(name_en="Coventry City") == "考文垂"
    assert resolve_club_cn(name_en="Hull City") == "赫尔城"
    assert resolve_club_cn(name_en="Schalke 04") == "沙尔克04"
    assert resolve_club_cn(name_en="SV Elversberg") == "埃尔弗斯贝格"
    assert resolve_club_cn(fd_id=1076) == "考文垂"
    # Critical FD ids (must not collide across leagues)
    assert resolve_club_cn(fd_id=100) == "罗马"
    assert resolve_club_cn(fd_id=29) == "帕德博恩"
    assert resolve_club_cn(fd_id=5890) == "莱切"
    assert resolve_club_cn(fd_id=5911) == "蒙扎"
    assert resolve_club_cn(fd_id=719) == "埃尔弗斯贝格"
    assert resolve_club_cn(fd_id=5335) == "桑坦德竞技"


def test_league_round_not_knockout():
    from service.score_pick import is_knockout_stage

    assert is_knockout_stage("第1轮") is False
    assert is_knockout_stage("第38轮") is False
    assert is_knockout_stage("联赛") is False
    assert is_knockout_stage("Round 12") is False
    assert is_knockout_stage("小组赛") is False
    assert is_knockout_stage("1/8决赛") is True
    assert is_knockout_stage("半决赛") is True
    assert is_knockout_stage("Round of 16") is True


def test_league_synthetic_crs_produces_scores():
    from service.score_pick import run_full_score_pipeline

    best, upset, all_picks, _ = run_full_score_pipeline(
        {},
        win_rate=62.0, draw_rate=22.0, lose_rate=16.0,
        expected_a=1.9, expected_b=0.8,
        stage="第1轮",
        rank_a=1, rank_b=19,
    )
    assert best and best[0] != "?"
    assert all(":" in s for s in best if s)
