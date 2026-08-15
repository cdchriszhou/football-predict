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
