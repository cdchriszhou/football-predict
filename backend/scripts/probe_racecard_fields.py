"""Probe racecard age/sex/rating parsing."""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from crawler.hkjc_client import HkjcClient
from crawler.hkjc_scraper import parse_racecard_html, fetch_meeting_with_graphql_fallback


async def main():
    c = HkjcClient()
    today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    for i in range(30):
        d = (today - timedelta(days=i)).isoformat()
        ds = d.replace("-", "/")
        for vc in ("ST", "HV"):
            url = (
                "https://racing.hkjc.com/racing/information/Chinese/Racing/RaceCard.aspx"
                f"?RaceDate={ds}&Racecourse={vc}&RaceNo=1"
            )
            try:
                html = await c.fetch_html(url)
            except Exception:
                continue
            if "6次近績" not in html and "6次近绩" not in html:
                continue
            race = parse_racecard_html(html, d, vc, 1)
            if not race or not race.get("runners"):
                continue
            r0 = race["runners"][0]
            print("HTML", d, vc, {k: r0.get(k) for k in ("name", "rating", "age", "sex", "horse_code")})
            m = await fetch_meeting_with_graphql_fallback(c, d, vc)
            if m and m.get("races"):
                r = m["races"][0]["runners"][0]
                print("MEETING", m.get("source"), {k: r.get(k) for k in ("name", "rating", "age", "sex")})
            return
    print("no racecard in 30 days")


if __name__ == "__main__":
    asyncio.run(main())
