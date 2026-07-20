import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def main():
    url = f"{HKJC_RACING_BASE}/RaceCard.aspx?RaceDate=2026/05/31&Racecourse=ST&RaceNo=1"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = (await c.get(url, headers=headers)).text
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    for line in text.split("\n"):
        if any(k in line for k in ("第", "場", "1200", "11", "沙田", "5月31")):
            if len(line) < 100:
                print(line)
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.select("table"):
        rows = table.select("tr")
        if not rows:
            continue
        h = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])]
        if any("6次" in x for x in h):
            print("HEADER", h)
            print("ROW1", [c.get_text(strip=True) for c in rows[1].find_all(["th","td"])])

asyncio.run(main())
