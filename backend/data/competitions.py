"""Competition registry — World Cup +五大联赛 + 体彩数字彩."""

from __future__ import annotations

COMPETITIONS: dict[str, dict] = {
    "worldcup-2026": {
        "slug": "worldcup-2026",
        "name_key": "worldcup2026",
        "short_name": "2026世界杯",
        "type": "international",
        "odds_api_sport_key": "soccer_fifa_world_cup",
        "football_data_code": "WC",
        "season_year": 2026,
        "sporttery_league_hints": ["世界", "世界杯", "World Cup", "FIFA", "世预赛", "国际"],
        "features": {
            "bracket": True,
            "tournament": True,
            "sporttery": True,
            "groups": True,
        },
        "opening_date": "2026-06-11T20:00:00Z",
        # Final kickoff 03:00 BJT; mark ended after full-time + ET buffer.
        "closing_date": "2026-07-19T22:00:00Z",
        "theme_color": "#1a237e",
        "timezone": "America/New_York",
        "timezone_label_key": "usa",
        "order": 0,
    },
    "premier-league": {
        "slug": "premier-league",
        "name_key": "premierLeague",
        "short_name": "英超",
        "type": "club",
        "odds_api_sport_key": "soccer_epl",
        "football_data_code": "PL",
        "season_year": 2025,
        "sporttery_league_hints": ["英超", "英格兰超级", "Premier", "English Premier"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2025-08-15T00:00:00Z",
        "closing_date": "2026-05-24T23:59:59Z",
        "theme_color": "#38003c",
        "timezone": "Europe/London",
        "timezone_label_key": "uk",
        "order": 1,
    },
    "la-liga": {
        "slug": "la-liga",
        "name_key": "laLiga",
        "short_name": "西甲",
        "type": "club",
        "odds_api_sport_key": "soccer_spain_la_liga",
        "football_data_code": "PD",
        "season_year": 2025,
        "sporttery_league_hints": ["西甲", "西班牙甲级", "La Liga"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2025-08-15T00:00:00Z",
        "closing_date": "2026-05-24T23:59:59Z",
        "theme_color": "#ee8707",
        "timezone": "Europe/Madrid",
        "timezone_label_key": "spain",
        "order": 2,
    },
    "serie-a": {
        "slug": "serie-a",
        "name_key": "serieA",
        "short_name": "意甲",
        "type": "club",
        "odds_api_sport_key": "soccer_italy_serie_a",
        "football_data_code": "SA",
        "season_year": 2025,
        "sporttery_league_hints": ["意甲", "意大利甲级", "Serie A"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2025-08-23T00:00:00Z",
        "closing_date": "2026-05-24T23:59:59Z",
        "theme_color": "#008fd7",
        "timezone": "Europe/Rome",
        "timezone_label_key": "italy",
        "order": 3,
    },
    "bundesliga": {
        "slug": "bundesliga",
        "name_key": "bundesliga",
        "short_name": "德甲",
        "type": "club",
        "odds_api_sport_key": "soccer_germany_bundesliga",
        "football_data_code": "BL1",
        "season_year": 2025,
        "sporttery_league_hints": ["德甲", "德国甲级", "Bundesliga"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2025-08-22T00:00:00Z",
        "closing_date": "2026-05-16T23:59:59Z",
        "theme_color": "#d20515",
        "timezone": "Europe/Berlin",
        "timezone_label_key": "germany",
        "order": 4,
    },
    "ligue-1": {
        "slug": "ligue-1",
        "name_key": "ligue1",
        "short_name": "法甲",
        "type": "club",
        "odds_api_sport_key": "soccer_france_ligue_one",
        "football_data_code": "FL1",
        "season_year": 2025,
        "sporttery_league_hints": ["法甲", "法国甲级", "Ligue 1"],
        "features": {
            "bracket": False,
            "tournament": False,
            "sporttery": True,
            "groups": False,
        },
        "opening_date": "2025-08-15T00:00:00Z",
        "closing_date": "2026-05-16T23:59:59Z",
        "theme_color": "#091c3e",
        "timezone": "Europe/Paris",
        "timezone_label_key": "france",
        "order": 5,
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
        "order": 6,
    },
}

DEFAULT_COMPETITION = "worldcup-2026"


def get_competition(slug: str) -> dict | None:
    return COMPETITIONS.get(slug)


def list_competitions() -> list[dict]:
    return sorted(COMPETITIONS.values(), key=lambda c: c["order"])


def is_valid_competition(slug: str) -> bool:
    return slug in COMPETITIONS


def league_hints_for(slug: str) -> tuple[str, ...]:
    comp = get_competition(slug)
    if not comp:
        return ()
    return tuple(comp.get("sporttery_league_hints") or ())
