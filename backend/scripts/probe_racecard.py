"""Parse RaceCard HTML sample."""
import asyncio
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE
import httpx

async def main():
    url = f"{HKJC_RACING_BASE}/RaceCard.aspx"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = await c.get(url, headers=headers)
    soup = BeautifulSoup(html.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    for line in text.split("\n"):
        if any(k in line for k in ("沙田", "跑馬", "第", "場", "米", "班")):
            if len(line) < 120:
                print(line)
    tables = soup.select("table")
    for ti, table in enumerate(tables[:3]):
        rows = table.select("tr")
        print(f"\nTABLE {ti} rows={len(rows)}")
        for row in rows[:3]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th","td"])]
            print(cells[:12])

asyncio.run(main())
