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


# Common football-data / media variants (beyond LEAGUE_TEAMS English names)
_EXTRA_VARIANTS: list[tuple[str, str]] = [
    ("Man City", "曼城"),
    ("Man United", "曼联"),
    ("Tottenham", "热刺"),
    ("Newcastle", "纽卡斯尔联"),
    ("West Ham", "西汉姆联"),
    ("West Ham United", "西汉姆联"),
    ("Wolverhampton Wanderers", "狼队"),
    ("Wolves", "狼队"),
    ("Brighton & Hove Albion", "布莱顿"),
    ("Nottingham Forest", "诺丁汉森林"),
    ("Nott'm Forest", "诺丁汉森林"),
    ("Coventry", "考文垂"),
    ("Hull", "赫尔城"),
    ("Leeds", "利兹联"),
    ("Real Madrid CF", "皇马"),
    ("FC Barcelona", "巴萨"),
    ("Club Atlético de Madrid", "马竞"),
    ("Atlético Madrid", "马竞"),
    ("Athletic Club", "毕尔巴鄂"),
    ("Deportivo de La Coruña", "拉科鲁尼亚"),
    ("RC Deportivo de La Coruña", "拉科鲁尼亚"),
    ("Racing de Santander", "桑坦德竞技"),
    ("Real Racing Club", "桑坦德竞技"),
    ("Real Racing Club de Santander", "桑坦德竞技"),
    ("Málaga CF", "马拉加"),
    ("Málaga", "马拉加"),
    ("FC Internazionale Milano", "国际米兰"),
    ("Internazionale", "国际米兰"),
    ("Inter", "国际米兰"),
    ("AC Milan", "AC米兰"),
    ("AS Roma", "罗马"),
    ("Hellas Verona FC", "维罗纳"),
    ("US Sassuolo Calcio", "萨索洛"),
    ("Frosinone Calcio", "弗罗西诺内"),
    ("AC Monza", "蒙扎"),
    ("Monza", "蒙扎"),
    ("US Lecce", "莱切"),
    ("Lecce", "莱切"),
    ("FC Bayern München", "拜仁慕尼黑"),
    ("FC Bayern Munich", "拜仁慕尼黑"),
    ("BVB", "多特蒙德"),
    ("RasenBallsport Leipzig", "莱比锡"),
    ("1. FC Köln", "科隆"),
    ("1. FC Cologne", "科隆"),
    ("FC Cologne", "科隆"),
    ("Hamburger SV", "汉堡"),
    ("HSV", "汉堡"),
    ("FC Schalke 04", "沙尔克04"),
    ("Schalke", "沙尔克04"),
    ("SC Paderborn 07", "帕德博恩"),
    ("Paderborn", "帕德博恩"),
    ("SV 07 Elversberg", "埃尔弗斯贝格"),
    ("SV Elversberg", "埃尔弗斯贝格"),
    ("Elversberg", "埃尔弗斯贝格"),
    ("Paris SG", "巴黎圣日耳曼"),
    ("PSG", "巴黎圣日耳曼"),
    ("Olympique de Marseille", "马赛"),
    ("Olympique Lyonnais", "里昂"),
    ("LOSC Lille", "里尔"),
    ("Stade Rennais FC", "雷恩"),
    ("Stade Brestois 29", "布雷斯特"),
    ("ESTAC Troyes", "特鲁瓦"),
    ("Le Mans FC", "勒芒"),
    ("Le Mans", "勒芒"),
    ("Paris FC", "巴黎FC"),
    ("FC Lorient", "洛里昂"),
]

for _en, _cn in _EXTRA_VARIANTS:
    _register(_en, _cn)


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
            if base.lower() in EN_TO_CN_CLUB:
                return EN_TO_CN_CLUB[base.lower()]
    return en
