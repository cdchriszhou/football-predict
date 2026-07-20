"""
Wikipedia squad scraper for 2026 FIFA World Cup.

Fetches and parses the "2026 FIFA World Cup squads" page to extract
real player rosters as teams announce them.

Anti-bot measures (reusing patterns from odds_scraper.py):
  - Rotating User-Agent pool
  - Request rate limiting
  - Session/cookie persistence
  - Exponential backoff on failure
"""
import asyncio
import random
import re
import time
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from utils.logger import logger

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"

_last_request = 0.0
_session: Optional[httpx.AsyncClient] = None


def _ua() -> str:
    return random.choice(USER_AGENTS)


async def _rate_limit(min_interval: float = 1.5):
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < min_interval:
        await asyncio.sleep(min_interval - elapsed + random.uniform(0, 0.5))
    _last_request = time.monotonic()


async def _get_session() -> httpx.AsyncClient:
    global _session
    if _session is None:
        _session = httpx.AsyncClient(
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
            },
            follow_redirects=True,
            timeout=15,
        )
    return _session


# ── Wikipedia HTML fetching ──────────────────────────────────────────

async def fetch_wikipedia_squads() -> Optional[str]:
    """Fetch the Wikipedia squads page HTML. Returns None on failure."""
    await _rate_limit(1.5)
    session = await _get_session()
    session.headers.update({
        "User-Agent": _ua(),
        "Referer": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup",
    })

    for attempt in range(2):
        try:
            resp = await session.get(WIKIPEDIA_URL)
            if resp.status_code == 200:
                logger.info(f"Wikipedia squads page fetched ({len(resp.text)} bytes)")
                return resp.text
            elif resp.status_code in (429, 503):
                wait = (attempt + 1) * 2
                logger.warning(f"Wikipedia returned {resp.status_code}, retry in {wait}s")
                await asyncio.sleep(wait)
            else:
                logger.warning(f"Wikipedia returned HTTP {resp.status_code}")
                return None
        except httpx.TimeoutException:
            logger.warning(f"Wikipedia fetch timeout (attempt {attempt + 1}/2)")
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Wikipedia fetch error: {e} (attempt {attempt + 1}/2)")
            await asyncio.sleep(2)

    logger.warning("Wikipedia squads page unreachable after 2 attempts, using fallback data")
    return None


# ── HTML parsing ─────────────────────────────────────────────────────

# Wikipedia uses standardized section headings. Group headings contain
# <span class="mw-headline" id="Group_A">Group A</span>.
# Team headings appear as <h3> or <h4> under each group.
# Each team has a <table class="wikitable"> with squad data.

# Wikipedia column header texts → our column index
_WIKI_COLUMNS = {
    "no.": "number",
    "pos.": "position",
    "player": "name",
    "date of birth (age)": "dob_age",
    "caps": "caps",
    "goals": "goals",
    "club": "club",
}


def _normalize_header(text: str) -> str:
    return text.strip().lower().rstrip(".")


def _detect_columns(headers: list[str]) -> dict[str, int]:
    """Map Wikipedia column headers to column indices."""
    col_map = {}
    for i, h in enumerate(headers):
        norm = _normalize_header(h)
        if norm in _WIKI_COLUMNS:
            col_map[_WIKI_COLUMNS[norm]] = i
        # Also try partial match for "date of birth" variant
        elif "date of birth" in norm or "dob" in norm:
            col_map["dob_age"] = i
    return col_map


def _calculate_age(dob_text: str, ref_year: int = 2026) -> Optional[int]:
    """Parse birth date and calculate age as of June 2026.

    Wikipedia format examples:
      "12 March 1998 (age 28)"
      "1998-03-12 (age 28)"
      "(1998-03-12)28"  (variant)
    """
    # Try to extract age from "(age NN)" pattern first
    age_match = re.search(r'\(age\s*(\d{1,2})\)', dob_text, re.IGNORECASE)
    if age_match:
        return int(age_match.group(1))

    # Try to extract birth year from date patterns
    year_match = re.search(r'(?:19|20)(\d{2})', dob_text)
    if year_match:
        year = int(year_match.group(0))
        return ref_year - year

    # Try standalone number at end in parentheses: "(1998-03-12)28"
    age_match2 = re.search(r'\)(\d{1,2})$', dob_text.strip())
    if age_match2:
        return int(age_match2.group(1))

    return None


def _parse_player_row(row, col_map: dict[str, int]) -> Optional[dict]:
    """Parse a single <tr> into a player dict. Returns None for non-player rows."""
    cells = row.find_all(["th", "td"])
    if not cells or len(cells) < 3:
        return None

    def _cell_text(idx: int) -> str:
        if idx in col_map and col_map[idx] < len(cells):
            return cells[col_map[idx]].get_text(strip=True)
        return ""

    # Check if this row has a valid jersey number (filters out header/separator rows)
    number_str = _cell_text(_find_col_idx(col_map, "number"))
    if not number_str:
        return None
    try:
        number = int(number_str)
    except ValueError:
        return None  # Not a player row

    name = _cell_text(_find_col_idx(col_map, "name"))
    if not name:
        return None

    position = _cell_text(_find_col_idx(col_map, "position"))
    dob_age = _cell_text(_find_col_idx(col_map, "dob_age"))
    caps_str = _cell_text(_find_col_idx(col_map, "caps"))
    goals_str = _cell_text(_find_col_idx(col_map, "goals"))
    club = _cell_text(_find_col_idx(col_map, "club"))

    age = _calculate_age(dob_age) if dob_age else None

    caps = None
    try:
        caps = int(caps_str) if caps_str else None
    except ValueError:
        pass

    goals = None
    try:
        goals = int(goals_str) if goals_str else None
    except ValueError:
        pass

    return {
        "number": number,
        "position": position,
        "name": name,
        "age": age,
        "caps": caps,
        "goals": goals,
        "club": club,
    }


def _find_col_idx(col_map: dict[str, int], key: str) -> int:
    """Get column index from map, using key or fallback positions."""
    return col_map.get(key, _DEFAULT_COL_FALLBACK.get(key, 0))


# Fallback column positions if header detection fails (standard Wikipedia order)
_DEFAULT_COL_FALLBACK = {
    "number": 0,
    "position": 1,
    "name": 2,
    "dob_age": 3,
    "caps": 4,
    "goals": 5,
    "club": 6,
}


def _extract_team_name(heading) -> Optional[str]:
    """Extract team name from a section heading element.

    Wikipedia headings typically contain just the country name,
    possibly with flag icons or '[edit]' links removed by get_text().
    """
    text = heading.get_text(strip=True)
    # Remove [edit] or [source] suffix
    text = re.sub(r'\s*\[(?:edit|source|editar|modifier).*?\]', '', text)
    return text.strip() or None


def _is_group_heading(heading) -> bool:
    """Check if heading text contains 'Group' followed by a letter."""
    text = heading.get_text(strip=True).lower()
    return bool(re.search(r'group\s+[a-l]', text))


def parse_squad_tables(html: str) -> dict[str, list[dict]]:
    """Parse Wikipedia HTML into {team_english_name: [player_dicts]}.

    Handles pages structured as:
      <h2>Group A</h2>
      <h3>Mexico</h3>
      <table class="wikitable">...</table>
      <h3>South Africa</h3>
      <table class="wikitable">...</table>
      ...
      <h2>Group B</h2>
      ...

    Returns empty dict if no teams could be parsed.
    """
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, list[dict]] = {}
    current_team: Optional[str] = None
    teams_found = 0
    players_found = 0

    # Find all relevant headings and tables
    # Strategy: iterate through siblings of the content area
    content = soup.find("div", id="mw-content-text") or soup.find("div", id="bodyContent") or soup
    if not content:
        content = soup

    # Find all wikitable elements and their preceding team headings
    headings = content.find_all(["h2", "h3", "h4", "h5"])

    for heading in headings:
        heading_text = heading.get_text(strip=True)
        # Remove edit links
        heading_text = re.sub(r'\s*\[(?:edit|source).*?\]', '', heading_text).strip()

        # Skip group headings, TOC, references, etc.
        if _is_group_heading(heading):
            continue
        if heading_text.lower() in ("contents", "references", "notes", "external links",
                                     "see also", "navigation", "2026 fifa world cup squads"):
            continue

        # Look for the wikitable immediately following this heading
        table = heading.find_next_sibling("table", class_="wikitable")
        if table is None:
            # Try: the wikitable might be nested inside a div
            next_elem = heading.find_next_sibling()
            if next_elem and next_elem.name == "div":
                table = next_elem.find("table", class_="wikitable")

        if table is None:
            continue

        players = _parse_wikitable(table)
        if len(players) >= 11:  # Valid squad has at least 11 players
            result[heading_text] = players
            teams_found += 1
            players_found += len(players)
        elif len(players) > 0:
            logger.warning(
                f"Team '{heading_text}' has only {len(players)} players in Wikipedia table, skipping"
            )

    logger.info(f"Parsed {teams_found} teams, {players_found} players from Wikipedia")
    return result


def _parse_wikitable(table) -> list[dict]:
    """Parse a single wikitable into a list of player dicts."""
    players = []
    rows = table.find_all("tr")
    col_map: dict[str, int] = {}

    for row in rows:
        # Detect header row
        th_cells = row.find_all("th")
        if th_cells and not col_map:
            headers = [th.get_text(strip=True) for th in th_cells]
            col_map = _detect_columns(headers)
            if col_map:
                continue  # Header row, skip

        # Parse player row
        if not col_map:
            # Try fallback: first row with td cells, use default positions
            if row.find("td"):
                # Use default column positions
                pass

        player = _parse_player_row(row, col_map if col_map else _DEFAULT_COL_FALLBACK)
        if player:
            players.append(player)

    return players


# ── Public entry point ───────────────────────────────────────────────

async def scrape_all_squads() -> dict[str, list[dict]]:
    """Fetch and parse Wikipedia for all team squads.

    Returns: {team_english_name: [player_dicts]}
    Each player dict: {number, position, name, age, caps, goals, club}

    Never raises — returns empty dict on any failure.
    """
    try:
        html = await fetch_wikipedia_squads()
        if html is None:
            return {}
        result = parse_squad_tables(html)
        return result
    except Exception as e:
        logger.error(f"scrape_all_squads failed: {e}", exc_info=True)
        return {}
