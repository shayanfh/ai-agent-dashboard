from io import BytesIO

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.storage import get_object_storage
from app.main import app
from app.modules.agents.models import Agent
from app.modules.knowledge_base.processor import chunk_text, extract_text


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_restaurant_and_car_rental_templates_are_public(client: AsyncClient):
    response = await client.get("/api/v1/knowledge-base/templates")
    assert response.status_code == 200
    templates = response.json()
    assert {item["business_type"] for item in templates} == {"restaurant", "car_rental"}
    assert all(len(item["items"]) >= 10 for item in templates)


@pytest.mark.asyncio
async def test_apply_template_is_idempotent_and_bumps_version(
    client: AsyncClient,
    admin_a_token: str,
    agent_a: Agent,
):
    payload = {"agent_id": str(agent_a.id)}
    first = await client.post(
        "/api/v1/knowledge-base/templates/restaurant/apply",
        json=payload,
        headers=_auth(admin_a_token),
    )
    assert first.status_code == 200
    assert first.json()["created"] >= 10
    assert first.json()["knowledge_version"] == 2

    second = await client.post(
        "/api/v1/knowledge-base/templates/restaurant/apply",
        json=payload,
        headers=_auth(admin_a_token),
    )
    assert second.status_code == 200
    assert second.json()["created"] == 0
    assert second.json()["skipped"] >= 10


@pytest.mark.asyncio
async def test_internal_snapshot_contains_agent_template_knowledge(
    client: AsyncClient,
    admin_a_token: str,
    agent_a: Agent,
):
    await client.post(
        "/api/v1/knowledge-base/templates/car_rental/apply",
        json={"agent_id": str(agent_a.id)},
        headers=_auth(admin_a_token),
    )
    response = await client.get(
        "/api/v1/internal/voice/knowledge-snapshot",
        params={"agent_id": str(agent_a.id)},
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
    )
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["agent_id"] == str(agent_a.id)
    assert snapshot["version"] >= 2
    assert any("security deposit" in item["title"].lower() for item in snapshot["entries"])


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def upload(self, source: BytesIO, *, key: str, content_type: str) -> str:
        self.objects[key] = source.read()
        return f"s3://test/{key}"

    async def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)


@pytest.mark.asyncio
async def test_direct_document_upload_stores_file_and_queues_processing(
    client: AsyncClient,
    admin_a_token: str,
    agent_a: Agent,
    monkeypatch: pytest.MonkeyPatch,
):
    storage = _FakeStorage()
    queued: list[str] = []
    app.dependency_overrides[get_object_storage] = lambda: storage
    monkeypatch.setattr(
        "app.modules.knowledge_base.service._queue_document",
        lambda document: queued.append(str(document.id)),
    )
    try:
        response = await client.post(
            "/api/v1/knowledge-base/documents/upload",
            data={"agent_id": str(agent_a.id)},
            files={"file": ("policy.txt", b"Our cancellation policy is 24 hours.", "text/plain")},
            headers=_auth(admin_a_token),
        )
    finally:
        app.dependency_overrides.pop(get_object_storage, None)
    assert response.status_code == 201, response.text
    assert response.json()["processing_status"] == "pending"
    assert response.json()["size_bytes"] == 36
    assert len(storage.objects) == 1
    assert queued == [response.json()["id"]]


def test_text_extraction_and_chunking_preserve_content():
    text = extract_text("سلام دنیا\n\nقوانین رزرو خودرو".encode(), "txt")
    chunks = chunk_text(text, size=200, overlap=20)
    assert chunks == ["سلام دنیا\n\nقوانین رزرو خودرو"]
