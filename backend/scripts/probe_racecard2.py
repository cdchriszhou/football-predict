import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def main():
    url = f"{HKJC_RACING_BASE}/RaceCard.aspx"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = (await c.get(url, headers=headers)).text
    soup = BeautifulSoup(html, "html.parser")
    # find race sections by headers containing 第 N 場
    for h in soup.find_all(["div", "td", "span", "a"]):
        t = h.get_text(strip=True)
        if re.match(r"第\s*\d+\s*場", t) and len(t) < 30:
            print("RACE HEADER:", t)
    tables = soup.select("table")
    for ti, table in enumerate(tables):
        rows = table.select("tr")
        if len(rows) < 4:
            continue
        hcells = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])]
        if "馬名" in "".join(hcells) or "马名" in "".join(hcells) or "馬匹" in "".join(hcells):
            print(f"\nRUNNER TABLE {ti} header={hcells}")
            for row in rows[1:4]:
                print([c.get_text(strip=True) for c in row.find_all(["th","td"])][:15])

asyncio.run(main())
