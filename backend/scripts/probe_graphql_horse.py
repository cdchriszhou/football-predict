import asyncio
import httpx

URL = "https://info.cld.hkjc.com/graphql/base/"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://bet.hkjc.com/",
    "Origin": "https://bet.hkjc.com",
    "Content-Type": "application/json",
}


async def try_fields(extra: str):
    q = f"""
    query raceMeetings($date: String, $venueCode: String) {{
      raceMeetings(date: $date, venueCode: $venueCode) {{
        races {{ runners {{ no horse {{ code {extra} }} }} }}
      }}
    }}
    """
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            URL,
            json={
                "operationName": "raceMeetings",
                "query": q,
                "variables": {"date": "2025-03-23", "venueCode": "ST"},
            },
            headers=HEADERS,
        )
    print("---", extra, r.status_code)
    print(r.text[:600])


async def main():
    for extra in ("", "age", "sex", "age sex", "horseAge", "gender"):
        await try_fields(extra)


if __name__ == "__main__":
    asyncio.run(main())
