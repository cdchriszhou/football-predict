"""Test meeting discovery count."""
import asyncio

from crawler.hkjc_client import HKJC_RACING_BASE, HkjcClient
from crawler.hkjc_scraper import discover_meetings, parse_results_all_dates


async def main():
    client = HkjcClient()
    html = await client.fetch_html(f"{HKJC_RACING_BASE}/ResultsAll.aspx")
    dates = parse_results_all_dates(html, limit=10)
    print("dates from select:", dates)

    discovered = await discover_meetings(client, limit=10)
    print("discovered:", len(discovered))
    for m in discovered:
        print(" ", m["id"], m["date"], m["venue"], m.get("featured"))


if __name__ == "__main__":
    asyncio.run(main())
