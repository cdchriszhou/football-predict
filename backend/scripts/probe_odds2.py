import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def main():
    url = f"{HKJC_RACING_BASE}/RaceCard.aspx?RaceDate=2026/05/31&Racecourse=ST&RaceNo=1"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = (await c.get(url, headers=headers)).text
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        href = a.get("href") or ""
        if "odd" in href.lower() or "Odd" in href or "赔率" in a.get_text():
            print(href[:120], a.get_text(strip=True)[:40])

asyncio.run(main())
