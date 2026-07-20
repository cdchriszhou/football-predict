"""Club English name variants → canonical Chinese names for五大联赛."""

from __future__ import annotations

from data.club_crests import CLUB_CREST_IDS
from data.league_seed import LEAGUE_TEAMS

# football-data.org team id -> Chinese canonical name
FD_ID_TO_CN: dict[int, str] = {v: k for k, v in CLUB_CREST_IDS.items()}

# English / API variants -> Chinese
EN_TO_CN_CLUB: dict[str, str] = {}

_SUFFIXES = (
    " FC", " CF", " SC", " AC", " AFC", " FK",
    " Hotspur", " United", " City",
)


def _norm_en(name: str) -> str:
    return (name or "").strip()


def _register(en: str, cn: str) -> None:
    en = _norm_en(en)
    if en:
        EN_TO_CN_CLUB[en] = cn
        EN_TO_CN_CLUB[en.lower()] = cn


for _slug, teams in LEAGUE_TEAMS.items():
    for cn, en, _rank in teams:
        _register(en, cn)
        _register(cn, cn)
        # Common football-data / media variants
        if en == "Manchester City":
            _register("Man City", cn)
        elif en == "Manchester United":
            _register("Man United", cn)
        elif en == "Tottenham Hotspur":
            _register("Tottenham", cn)
        elif en == "Newcastle United":
            _register("Newcastle", cn)
        elif en == "West Ham United":
            _register("West Ham", cn)
        elif en == "Wolverhampton":
            _register("Wolverhampton Wanderers", cn)
            _register("Wolves", cn)
        elif en == "Real Madrid":
            _register("Real Madrid CF", cn)
        elif en == "Barcelona":
            _register("FC Barcelona", cn)
        elif en == "Atletico Madrid":
            _register("Club Atlético de Madrid", cn)
            _register("Atlético Madrid", cn)
        elif en == "Inter Milan":
            _register("FC Internazionale Milano", cn)
            _register("Internazionale", cn)
        elif en == "AC Milan":
            _register("AC Milan", cn)
        elif en == "Bayern Munich":
            _register("FC Bayern München", cn)
            _register("FC Bayern Munich", cn)
        elif en == "Borussia Dortmund":
            _register("BVB", cn)
        elif en == "RB Leipzig":
            _register("RasenBallsport Leipzig", cn)
        elif en == "Paris Saint-Germain":
            _register("Paris SG", cn)
            _register("PSG", cn)
        elif en == "Nottingham Forest":
            _register("Nott'm Forest", cn)


def resolve_club_cn(*, fd_id: int | None = None, name_en: str | None = None) -> str:
    if fd_id and fd_id in FD_ID_TO_CN:
        return FD_ID_TO_CN[fd_id]
    en = _norm_en(name_en or "")
    if not en:
        return ""
    if en in EN_TO_CN_CLUB:
        return EN_TO_CN_CLUB[en]
    low = en.lower()
    if low in EN_TO_CN_CLUB:
        return EN_TO_CN_CLUB[low]
    for suffix in _SUFFIXES:
        if en.endswith(suffix):
            base = en[: -len(suffix)].strip()
            if base in EN_TO_CN_CLUB:
                return EN_TO_CN_CLUB[base]
    return en
