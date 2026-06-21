"""Inspect Fixture HTML structure."""
import asyncio
import re

from bs4 import BeautifulSoup

from crawler.hkjc_client import HKJC_RACING_BASE, HkjcClient


async def main():
    client = HkjcClient()
    html = await client.fetch_html(f"{HKJC_RACING_BASE}/Fixture.aspx?calmonth=6&calyear=2026")
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href*='RaceDate'], a[href*='racecard'], a[href*='RaceCard']")[:20]:
        print("A", a.get("href"), a.get_text(strip=True)[:40])
    for td in soup.select("td[class*='race'], td[class*='Race'], .raceDay, .race_day")[:20]:
        print("TD", td.get("class"), td.get_text(strip=True)[:40])
    # links with date
    for m in re.finditer(r"RaceDate=(\d{4}/\d{1,2}/\d{1,2})", html):
        print("RD", m.group(1))
        break
    # look for onclick or data attributes
    for el in soup.select("[onclick*='Race'], [data-date]")[:15]:
        print("EL", el.name, el.get("onclick"), el.get("data-date"), el.get_text(strip=True)[:20])
    # calendar table cells with numbers
    for td in soup.select("table td"):
        cls = " ".join(td.get("class") or [])
        txt = td.get_text(strip=True)
        if txt.isdigit() and int(txt) <= 31:
            if "ST" in cls or "HV" in cls or "race" in cls.lower() or td.select("a"):
                print("cell", txt, cls, td.select("a[href]"))


if __name__ == "__main__":
    asyncio.run(main())
