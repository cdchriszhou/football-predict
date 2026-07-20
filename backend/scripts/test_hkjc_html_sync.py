"""End-to-end HKJC HTML sync test."""
import asyncio
import json

from crawler.hkjc_client import HkjcClient
from crawler.hkjc_scraper import fetch_meeting_from_html


async def main():
    client = HkjcClient()
    meeting = await fetch_meeting_from_html(client, "2026-05-31", "ST", max_races=2)
    if not meeting:
        print("FAILED: no meeting")
        return
    print(json.dumps({
        "id": meeting["id"],
        "date": meeting["date"],
        "venue": meeting["venue"],
        "races": len(meeting["races"]),
        "race1_runners": len(meeting["races"][0]["runners"]) if meeting["races"] else 0,
        "sample_runner": meeting["races"][0]["runners"][0] if meeting["races"] and meeting["races"][0]["runners"] else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
