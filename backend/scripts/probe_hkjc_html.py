"""Probe HKJC HTML pages structure."""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from crawler.hkjc_client import HKJC_RACING_BASE, DEFAULT_HEADERS


async def fetch(url):
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url, headers=headers)
    print(url, r.status_code, len(r.text))
    return r.text


async def main():
    urls = [
        f"{HKJC_RACING_BASE}/RaceCard.aspx",
        f"{HKJC_RACING_BASE}/LocalResults.aspx",
        f"{HKJC_RACING_BASE}/ResultsAll.aspx",
    ]
    for u in urls:
        html = await fetch(u)
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string if soup.title else ""
        print(" title:", title)
        links = [a.get("href") for a in soup.select("a") if a.get("href") and "RaceDate" in a.get("href", "")]
        print(" race links:", links[:5])
        tables = len(soup.select("table"))
        print(" tables:", tables)

    d = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    url = f"{HKJC_RACING_BASE}/LocalResults.aspx?RaceDate={d.strftime('%Y/%m/%d')}&Racecourse=ST&RaceNo=1"
    html = await fetch(url)
    open("_hkjc_sample.html", "w", encoding="utf-8").write(html[:50000])
    print("saved sample")


if __name__ == "__main__":
    asyncio.run(main())
