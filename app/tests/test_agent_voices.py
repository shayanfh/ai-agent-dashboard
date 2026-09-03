from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.modules.agents.voice_catalog import ElevenLabsVoiceCatalog


def voice_settings() -> Settings:
    return Settings(
        _env_file=None,
        ELEVENLABS_API_KEY="elevenlabs-secret",
        ELEVENLABS_API_BASE_URL="https://elevenlabs.test",
        ELEVENLABS_VOICE_CACHE_SECONDS=300,
    )


@pytest.mark.asyncio
async def test_voice_catalog_merges_all_my_voice_and_library_pages_and_caches():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["xi-api-key"] == "elevenlabs-secret"
        if request.url.path == "/v2/voices":
            token = request.url.params.get("next_page_token")
            if token is None:
                return httpx.Response(
                    200,
                    json={
                        "voices": [{"voice_id": "mine-2", "name": "Zulu"}],
                        "has_more": True,
                        "next_page_token": "mine-page-2",
                    },
                )
            assert token == "mine-page-2"
            return httpx.Response(
                200,
                json={
                    "voices": [{"voice_id": "shared-1", "name": "My Alpha"}],
                    "has_more": False,
                },
            )

        assert request.url.path == "/v1/shared-voices"
        page = int(request.url.params["page"])
        assert request.url.params["page_size"] == "100"
        if page == 0:
            return httpx.Response(
                200,
                json={
                    "voices": [
                        {
                            "public_owner_id": "owner-1",
                            "voice_id": "shared-1",
                            "name": "Public Alpha",
                            "gender": "female",
                        }
                    ],
                    "has_more": True,
                },
            )
        assert page == 1
        return httpx.Response(
            200,
            json={
                "voices": [
                    {
                        "public_owner_id": "owner-2",
                        "voice_id": "shared-2",
                        "name": "Beta",
                    }
                ],
                "has_more": False,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://elevenlabs.test"
    ) as client:
        catalog = ElevenLabsVoiceCatalog(voice_settings(), client=client)
        first = await catalog.list_voices()
        second = await catalog.list_voices()

    assert [voice.voice_id for voice in first.voices] == [
        "shared-2",
        "shared-1",
        "mine-2",
    ]
    assert first.total == 3
    assert first.cached is False
    assert second.cached is True
    by_id = {voice.voice_id: voice for voice in first.voices}
    assert by_id["shared-1"].name == "My Alpha"
    assert by_id["shared-1"].in_my_voices is True
    assert by_id["shared-1"].public_owner_id is None
    assert by_id["shared-2"].in_my_voices is False
    assert by_id["shared-2"].public_owner_id == "owner-2"
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_agent_voice_endpoint_requires_admin_and_hides_verified_languages(
    client, admin_a_token, operator_a_token, monkeypatch
):
    list_voices = AsyncMock(
        return_value={
            "voices": [
                {
                    "voice_id": "voice-1",
                    "name": "Demo Voice",
                    "labels": {"accent": "american"},
                    "verified_languages": [{"language": "en"}],
                    "in_my_voices": False,
                    "public_owner_id": "owner-1",
                }
            ],
            "total": 1,
            "cached": False,
        }
    )
    monkeypatch.setattr("app.modules.agents.router.voice_catalog.list_voices", list_voices)

    forbidden = await client.get(
        "/api/v1/agents/voices",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    response = await client.get(
        "/api/v1/agents/voices?force_refresh=true",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    voice = response.json()["voices"][0]
    assert voice["voice_id"] == "voice-1"
    assert voice["public_owner_id"] == "owner-1"
    assert voice["in_my_voices"] is False
    assert "verified_languages" not in voice
    list_voices.assert_awaited_once_with(force_refresh=True)


@pytest.mark.asyncio
async def test_selected_library_voice_is_imported_automatically():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v2/voices":
            return httpx.Response(200, json={"voices": [], "has_more": False})
        if request.url.path == "/v1/shared-voices":
            return httpx.Response(
                200,
                json={
                    "voices": [
                        {
                            "public_owner_id": "owner-1",
                            "voice_id": "shared-1",
                            "name": "Sales Voice",
                        }
                    ],
                    "has_more": False,
                },
            )
        assert request.url.path == "/v1/voices/add/owner-1/shared-1"
        assert request.content == b'{"new_name":"Sales Voice"}'
        return httpx.Response(200, json={"voice_id": "shared-1"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://elevenlabs.test"
    ) as client:
        catalog = ElevenLabsVoiceCatalog(voice_settings(), client=client)
        imported = await catalog.ensure_voice_in_my_voices("shared-1")

    assert imported is True
    assert catalog._voices is None
    assert [request.url.path for request in requests] == [
        "/v2/voices",
        "/v1/shared-voices",
        "/v1/voices/add/owner-1/shared-1",
    ]


@pytest.mark.asyncio
async def test_my_voice_selection_does_not_import_again():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "voices": [{"voice_id": "mine-1", "name": "Already mine"}],
                "has_more": False,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://elevenlabs.test"
    ) as client:
        imported = await ElevenLabsVoiceCatalog(
            voice_settings(), client=client
        ).ensure_voice_in_my_voices("mine-1")

    assert imported is False
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_unknown_voice_is_rejected():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"voices": [], "has_more": False})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://elevenlabs.test"
    ) as client:
        catalog = ElevenLabsVoiceCatalog(voice_settings(), client=client)
        with pytest.raises(ValidationError) as exc_info:
            await catalog.ensure_voice_in_my_voices("missing")

    assert getattr(exc_info.value, "detail", {}).get("code") == "VALIDATION_ERROR"
