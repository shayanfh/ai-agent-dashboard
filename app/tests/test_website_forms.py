import json

import httpx
import pytest

from app.core.config import settings
from app.modules.website_forms.voice_preview import (
    GREETING_TEMPLATE,
    VoicePreviewRequest,
    VoicePreviewService,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def website_api_key(monkeypatch):
    monkeypatch.setattr(settings, "WEBSITE_API_KEY", "test-website-api-key")


def _headers():
    return {"Authorization": f"Bearer {settings.WEBSITE_API_KEY}"}


async def test_contact_requires_api_key(client):
    response = await client.post("/api/v1/public/contact", json={})
    assert response.status_code == 401


async def test_contact_is_saved(client):
    response = await client.post(
        "/api/v1/public/contact",
        headers=_headers(),
        json={
            "name": "Jane Doe",
            "email": "JANE@example.com",
            "company_name": "Example Inc",
            "subject": "AI receptionist",
            "message": "Please contact me.",
        },
    )
    assert response.status_code == 201
    assert response.json()["message"] == "Contact request received"


async def test_contact_sends_notification(client, monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "WEBSITE_NOTIFICATION_EMAIL", "shayan@mozaicweb.com")
    monkeypatch.setattr(
        "app.modules.website_forms.router.EmailService.send_message",
        lambda self, recipient, subject, body: sent.append((recipient, subject, body)),
    )
    response = await client.post(
        "/api/v1/public/contact",
        headers=_headers(),
        json={"name": "Jane Doe", "email": "jane@example.com", "company_name": "Example Inc"},
    )
    assert response.status_code == 201
    assert sent[0][0] == "shayan@mozaicweb.com"
    assert "jane@example.com" in sent[0][2]


async def test_demo_request_is_saved(client):
    response = await client.post(
        "/api/v1/public/demo-request",
        headers=_headers(),
        json={
            "name": "John Doe",
            "email": "john@example.com",
            "company_name": "Restaurant",
            "monthly_call_volume": "500",
            "industry": "restaurant",
            "marketing_consent": True,
        },
    )
    assert response.status_code == 201


async def test_newsletter_is_idempotent(client):
    payload = {"email": "news@example.com", "marketing_consent": True}
    first = await client.post("/api/v1/public/newsletter", headers=_headers(), json=payload)
    second = await client.post("/api/v1/public/newsletter", headers=_headers(), json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_voice_preview_requires_api_key(client):
    response = await client.post(
        "/api/v1/public/voice-preview",
        json={"company_name": "Acme", "voice": "coral"},
    )
    assert response.status_code == 401


async def test_voice_preview_returns_generated_mp3(client, monkeypatch):
    captured = {}

    async def generate(_self, data):
        captured["company_name"] = data.company_name
        captured["voice"] = data.voice
        return b"ID3-demo-audio"

    monkeypatch.setattr(
        "app.modules.website_forms.router.VoicePreviewService.generate",
        generate,
    )
    response = await client.post(
        "/api/v1/public/voice-preview",
        headers=_headers(),
        json={"company_name": "  Acme   Pizza  ", "voice": "nova"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content == b"ID3-demo-audio"
    assert captured == {"company_name": "Acme Pizza", "voice": "nova"}


async def test_voice_preview_rejects_unknown_voice(client):
    response = await client.post(
        "/api/v1/public/voice-preview",
        headers=_headers(),
        json={"company_name": "Acme", "voice": "unknown"},
    )
    assert response.status_code == 422


async def test_voice_preview_service_sends_fixed_greeting(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(settings, "TTS_PREVIEW_MODEL", "tts-1")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/audio/speech"
        assert request.headers["authorization"] == "Bearer test-openai-key"
        assert json.loads(request.content) == {
            "model": "tts-1",
            "input": GREETING_TEMPLATE.format("Acme Pizza"),
            "voice": "cedar",
            "response_format": "mp3",
        }
        return httpx.Response(200, content=b"ID3-openai-audio")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com",
    ) as http_client:
        audio = await VoicePreviewService(http_client).generate(
            VoicePreviewRequest(company_name="Acme Pizza", voice="cedar")
        )

    assert audio == b"ID3-openai-audio"
