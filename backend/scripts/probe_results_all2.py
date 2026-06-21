import asyncio, httpx, re
from bs4 import BeautifulSoup
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

async def main():
    url = f"{HKJC_RACING_BASE}/ResultsAll.aspx"
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        html = (await c.get(url, headers=headers)).text
    dates = re.findall(r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}/\d{1,2}/\d{1,2})", html)
    print("date patterns", sorted(set(dates), reverse=True)[:15])
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select("table tr")[:20]:
        t = row.get_text(" ", strip=True)
        if "沙田" in t or "跑馬" in t or "ST" in t:
            print(t[:120])

asyncio.run(main())
