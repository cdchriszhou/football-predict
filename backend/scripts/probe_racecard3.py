import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def main():
    url = f"{HKJC_RACING_BASE}/RaceCard.aspx"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = (await c.get(url, headers=headers)).text
    soup = BeautifulSoup(html, "html.parser")
    runner_tables = []
    for ti, table in enumerate(soup.select("table")):
        rows = table.select("tr")
        if not rows:
            continue
        h = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])]
        joined = "".join(h)
        if "6次近績" in joined or "6次近绩" in joined or ("馬名" in joined and "檔位" in joined):
            runner_tables.append((ti, len(rows)-1, h[:8]))
    print("runner tables:", len(runner_tables))
    for x in runner_tables[:15]:
        print(x)

asyncio.run(main())
