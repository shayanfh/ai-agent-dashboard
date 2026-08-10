import pytest

from app.core.config import settings

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
