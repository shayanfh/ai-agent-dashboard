import asyncio
import httpx


ELEVENLABS_API_KEY = "sk_7515336c43e1e4c5bd46cdede83d274f7a57644c33487f6d"


async def main():
    next_page_token = None

    params: dict[str, str | int | bool] = {
        "page_size": 100,
        "include_total_count": False,
        "sort": "name",
        "sort_direction": "asc",
    }

    if next_page_token:
        params["next_page_token"] = next_page_token

    async with httpx.AsyncClient(
        base_url="https://api.elevenlabs.io",
        timeout=30.0,
    ) as client:
        response = await client.get(
            "/v2/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            params=params,
        )

        print("Status:", response.status_code)
        print("URL:", response.request.url)

        try:
            print(response.json())
        except Exception:
            print(response.text)


if __name__ == "__main__":
    asyncio.run(main())