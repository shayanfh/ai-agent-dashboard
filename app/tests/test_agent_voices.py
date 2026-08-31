import httpx
import pytest

from app.core.config import Settings
from app.modules.agents.voice_catalog import ElevenLabsVoiceCatalog


def voice_settings() -> Settings:
    return Settings(
        _env_file=None,
        ELEVENLABS_API_KEY="elevenlabs-secret",
        ELEVENLABS_API_BASE_URL="https://elevenlabs.test",
        ELEVENLABS_VOICE_CACHE_SECONDS=300,
    )


@pytest.mark.asyncio
async def test_voice_catalog_fetches_every_page_and_caches_results():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["xi-api-key"] == "elevenlabs-secret"
        token = request.url.params.get("next_page_token")
        if token is None:
            return httpx.Response(
                200,
                json={
                    "voices": [
                        {
                            "voice_id": "voice-b",
                            "name": "Beta",
                            "category": "premade",
                            "preview_url": "https://audio.test/beta.mp3",
                            "labels": {"gender": "female"},
                        }
                    ],
                    "has_more": True,
                    "next_page_token": "page-2",
                },
            )
        assert token == "page-2"
        return httpx.Response(
            200,
            json={
                "voices": [
                    {
                        "voice_id": "voice-a",
                        "name": "Alpha",
                        "category": "cloned",
                        "verified_languages": [{"language": "en"}],
                    }
                ],
                "has_more": False,
                "next_page_token": None,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://elevenlabs.test",
    ) as client:
        catalog = ElevenLabsVoiceCatalog(voice_settings(), client=client)
        first = await catalog.list_voices()
        second = await catalog.list_voices()

    assert [voice.voice_id for voice in first.voices] == ["voice-a", "voice-b"]
    assert first.total == 2
    assert first.cached is False
    assert second.cached is True
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_agent_voice_endpoint_requires_admin_and_returns_catalog(
    client,
    admin_a_token,
    operator_a_token,
    monkeypatch,
):
    async def list_voices(*, force_refresh: bool = False):
        assert force_refresh is False
        return {
            "voices": [
                {
                    "voice_id": "voice-1",
                    "name": "Demo Voice",
                    "category": "premade",
                    "preview_url": "https://audio.test/demo.mp3",
                    "labels": {"accent": "american"},
                    "verified_languages": [],
                }
            ],
            "total": 1,
            "cached": False,
        }

    monkeypatch.setattr(
        "app.modules.agents.router.voice_catalog.list_voices",
        list_voices,
    )

    forbidden = await client.get(
        "/api/v1/agents/voices",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    response = await client.get(
        "/api/v1/agents/voices",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json()["voices"][0]["voice_id"] == "voice-1"
