"""Data source classification — predictions must use verified real sources only."""

REAL_EUROPEAN_SOURCES = frozenset({
    "the-odds-api",
    "european",
})
REAL_MACAU_SOURCES = frozenset({
    "the-odds-api",
    "macau",
    "asian_handicap",
})
REAL_SPORTTERY_SOURCES = frozenset({
    "sporttery.cn",
})


def _source_tag(source: str) -> str:
    return (source or "").lower()


def is_real_european(source: str) -> bool:
    s = _source_tag(source)
    if not s or "derived" in s:
        return False
    return any(k in s for k in REAL_EUROPEAN_SOURCES)


def is_real_macau(source: str) -> bool:
    s = _source_tag(source)
    if not s or "derived" in s:
        return False
    return any(k in s for k in REAL_MACAU_SOURCES)


def is_real_sporttery(source: str) -> bool:
    return "sporttery" in _source_tag(source)


def is_real_market_odds(european: dict | None, macau: dict | None) -> bool:
    """At least one real external bookmaker market is available."""
    if european and european.get("win_win") and is_real_european(european.get("source", "")):
        return True
    if macau and macau.get("win_win") and is_real_macau(macau.get("source", "")):
        return True
    return False


def meta_has_real_markets(meta: dict | None) -> bool:
    if not meta:
        return False
    return is_real_market_odds(meta.get("european"), meta.get("macau"))
