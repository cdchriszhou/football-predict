"""Manual HKJC API connectivity test."""
import asyncio
import json
import sys

import httpx

URL = "https://info.cld.hkjc.com/graphql/base/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://bet.hkjc.com/",
    "Origin": "https://bet.hkjc.com",
    "Content-Type": "application/json",
}


async def post(name: str, query: str, variables: dict | None = None):
    payload = {"operationName": name, "query": query, "variables": variables or {}}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(URL, json=payload, headers=HEADERS)
    print(f"\n=== {name} status={r.status_code} ===")
    print(r.text[:1200])


async def main():
    await post("active", "query active { raceMeetings { id venueCode date status } }")
    await post(
        "raceMeetings",
        "query raceMeetings($date: String, $venueCode: String) { raceMeetings(date: $date, venueCode: $venueCode) { id venueCode date races { no distance runners { no name_ch winOdds jockey { name_ch } trainer { name_ch } barrierDrawNumber last6run currentRating handicapWeight } } } }",
        {"date": "2025-05-25", "venueCode": "ST"},
    )

    from crawler.hkjc_client import HkjcClient
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    client = HkjcClient()
    today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    for i in range(14):
        d = today - timedelta(days=i)
        for vc in ("ST", "HV"):
            res = await client.fetch_race_result(d, vc, 1)
            if res:
                print(f"\nHTML result OK: {d} {vc}", json.dumps(res, ensure_ascii=False)[:400])
                return
    print("\nNo HTML results found in 14 days")


if __name__ == "__main__":
    asyncio.run(main())
