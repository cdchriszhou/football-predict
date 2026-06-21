import asyncio, httpx
from crawler.hkjc_client import DEFAULT_HEADERS, HKJC_RACING_BASE

PAGES = [
    "OddsWin.aspx", "OddsWP.aspx", "Odds.aspx",
    "WinOdds.aspx", "LocalResults.aspx",
]

async def main():
    headers = {k: v for k, v in DEFAULT_HEADERS.items() if k != "Content-Type"}
    qs = "?RaceDate=2026/05/31&Racecourse=ST&RaceNo=1"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        for p in PAGES:
            url = f"{HKJC_RACING_BASE}/{p}{qs}"
            try:
                r = await c.get(url, headers=headers)
                has_odds = "獨贏" in r.text or "赔率" in r.text or "Win Odds" in r.text
                print(p, r.status_code, len(r.text), has_odds)
            except Exception as e:
                print(p, e)

asyncio.run(main())
