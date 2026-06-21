import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def main():
    url = f"{HKJC_RACING_BASE}/ResultsAll.aspx"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = (await c.get(url, headers=headers)).text
    soup = BeautifulSoup(html, "html.parser")
    dates = set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        m = re.search(r"RaceDate=(\d{4}/\d{2}/\d{2})", href)
        if m:
            dates.add(m.group(1))
    print("dates found", len(dates), sorted(dates, reverse=True)[:10])

asyncio.run(main())
