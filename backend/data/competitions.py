"""Competition registry — 五大联赛 + 体彩数字彩."""

from __future__ import annotations

COMPETITIONS: dict[str, dict] = {
    "premier-league": {
        "slug": "premier-league",
        "name_key": "premierLeague",
        "short_name": "英超",
        "type": "club",
        "odds_api_sport_key": "soccer_epl",
        "football_data_code": "PL",
        "season_year": 2026,
        "sporttery_league_hints": ["英超", "英格兰超级", "Premier", "English Premier"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        # 2026/27: Arsenal vs Coventry, Fri 21 Aug 20:00 BST
        "opening_date": "2026-08-21T19:00:00Z",
        "closing_date": "2027-05-30T23:59:59Z",
        "theme_color": "#38003c",
        "timezone": "Europe/London",
        "timezone_label_key": "uk",
        "order": 0,
    },
    "la-liga": {
        "slug": "la-liga",
        "name_key": "laLiga",
        "short_name": "西甲",
        "type": "club",
        "odds_api_sport_key": "soccer_spain_la_liga",
        "football_data_code": "PD",
        "season_year": 2026,
        "sporttery_league_hints": ["西甲", "西班牙甲级", "La Liga"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        # 2026/27: earliest of the big five (mid-Aug)
        "opening_date": "2026-08-15T16:00:00Z",
        "closing_date": "2027-05-30T23:59:59Z",
        "theme_color": "#ee8707",
        "timezone": "Europe/Madrid",
        "timezone_label_key": "spain",
        "order": 1,
    },
    "serie-a": {
        "slug": "serie-a",
        "name_key": "serieA",
        "short_name": "意甲",
        "type": "club",
        "odds_api_sport_key": "soccer_italy_serie_a",
        "football_data_code": "SA",
        "season_year": 2026,
        "sporttery_league_hints": ["意甲", "意大利甲级", "Serie A"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2026-08-23T16:00:00Z",
        "closing_date": "2027-05-30T23:59:59Z",
        "theme_color": "#008fd7",
        "timezone": "Europe/Rome",
        "timezone_label_key": "italy",
        "order": 2,
    },
    "bundesliga": {
        "slug": "bundesliga",
        "name_key": "bundesliga",
        "short_name": "德甲",
        "type": "club",
        "odds_api_sport_key": "soccer_germany_bundesliga",
        "football_data_code": "BL1",
        "season_year": 2026,
        "sporttery_league_hints": ["德甲", "德国甲级", "Bundesliga"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        # 2026/27: Fri 28 Aug kickoff weekend
        "opening_date": "2026-08-28T18:30:00Z",
        "closing_date": "2027-05-22T23:59:59Z",
        "theme_color": "#d20515",
        "timezone": "Europe/Berlin",
        "timezone_label_key": "germany",
        "order": 3,
    },
    "ligue-1": {
        "slug": "ligue-1",
        "name_key": "ligue1",
        "short_name": "法甲",
        "type": "club",
        "odds_api_sport_key": "soccer_france_ligue_one",
        "football_data_code": "FL1",
        "season_year": 2026,
        "sporttery_league_hints": ["法甲", "法国甲级", "Ligue 1"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2026-08-23T15:00:00Z",
        "closing_date": "2027-05-29T23:59:59Z",
        "theme_color": "#091c3e",
        "timezone": "Europe/Paris",
        "timezone_label_key": "france",
        "order": 4,
    },
    "pailie": {
        "slug": "pailie",
        "name_key": "pailie",
        "short_name": "数字彩",
        "type": "digital",
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": False,
            "groups": False,
            "digital_lottery": True,
            "games": ["pl3", "pl5", "qxc", "ssq", "dlt", "fc3d"],
        },
        "opening_date": "2004-01-01T00:00:00Z",
        "closing_date": None,
        "theme_color": "#c62828",
        "timezone": "Asia/Shanghai",
        "timezone_label_key": "beijing",
        "order": 5,
    },
}

DEFAULT_COMPETITION = "premier-league"
WORLDCUP_SLUG = "worldcup-2026"


def get_competition(slug: str) -> dict | None:
    return COMPETITIONS.get(slug)


def is_worldcup_competition(slug: str | None) -> bool:
    return (slug or "") == WORLDCUP_SLUG


def is_club_competition(slug: str | None) -> bool:
    if not slug:
        return False
    return (get_competition(slug) or {}).get("type") == "club"


def list_competitions() -> list[dict]:
    return sorted(COMPETITIONS.values(), key=lambda c: c["order"])


def is_valid_competition(slug: str) -> bool:
    return slug in COMPETITIONS


def league_hints_for(slug: str) -> tuple[str, ...]:
    comp = get_competition(slug)
    if not comp:
        return ()
    return tuple(comp.get("sporttery_league_hints") or ())
