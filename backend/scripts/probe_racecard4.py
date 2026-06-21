import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def fetch(url):
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        return (await c.get(url, headers=headers)).text

async def count_runners(html):
    soup = BeautifulSoup(html, "html.parser")
    n = 0
    for table in soup.select("table"):
        rows = table.select("tr")
        if not rows:
            continue
        h = "".join(c.get_text(strip=True) for c in rows[0].find_all(["th","td"]))
        if "6次近績" in h or "6次近绩" in h:
            n += len(rows) - 1
    return n

async def main():
    base = f"{HKJC_RACING_BASE}/RaceCard.aspx"
    d = "2026/05/31"
    for race_no in range(1, 4):
        for qs in [
            f"?RaceDate={d}&Racecourse=ST&RaceNo={race_no}",
            f"?RaceDate={d}&RaceNo={race_no}",
        ]:
            html = await fetch(base + qs)
            runners = await count_runners(html)
            print(qs, "runners", runners)

asyncio.run(main())
