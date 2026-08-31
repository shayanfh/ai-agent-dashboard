"""
Agent CRUD tests.

Covers:
- Create agent (company admin)
- Read single agent
- List agents (with pagination metadata)
- Update agent (PATCH)
- Delete agent (soft-delete / 204)
- Agent templates endpoint (public, no auth required)
"""

import pytest
from httpx import AsyncClient

from app.modules.agents.models import Agent


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_agent_minimal(
    client: AsyncClient,
    admin_a_token: str,
    company_a,
):
    """Minimal agent creation with only required fields."""
    response = await client.post(
        "/api/v1/agents",
        json={"name": "Minimal Agent", "language": "en"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Minimal Agent"
    assert data["language"] == "en"
    assert "id" in data
    assert "company_id" in data


@pytest.mark.asyncio
async def test_create_agent_full(
    client: AsyncClient,
    admin_a_token: str,
    company_a,
):
    """Full agent creation with all optional fields."""
    response = await client.post(
        "/api/v1/agents",
        json={
            "name": "My Agent",
            "language": "en",
            "business_type": "car_rental",
            "llm_provider": "openai",
            "llm_model": "gpt-4.1-mini",
            "greeting_message": "Hello!",
            "system_prompt": "You are helpful.",
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Agent"
    assert data["language"] == "en"
    assert data["business_type"] == "car_rental"
    assert data["llm_provider"] == "openai"
    assert data["llm_model"] == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_realtime_agent_uses_fixed_models_and_selected_elevenlabs_voice(
    client: AsyncClient,
    admin_a_token: str,
):
    response = await client.post(
        "/api/v1/agents",
        json={
            "name": "Realtime Agent",
            "use_realtime": True,
            "voice_id": "custom-elevenlabs-voice",
            "voice_provider": "openai",
            "tts_provider": "openai",
            "tts_model": "customer-controlled-model",
            "stt_provider": "deepgram",
            "llm_provider": "openai",
            "llm_model": "customer-controlled-llm",
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["realtime_provider"] == "openai"
    assert data["realtime_model"] == "gpt-realtime"
    assert data["voice_provider"] == "elevenlabs"
    assert data["voice_id"] == "custom-elevenlabs-voice"
    assert data["tts_provider"] == "elevenlabs"
    assert data["tts_model"] == "eleven_flash_v2_5"
    assert data["stt_provider"] is None
    assert data["llm_provider"] is None


@pytest.mark.asyncio
async def test_realtime_model_is_not_customer_writable(
    client: AsyncClient,
    admin_a_token: str,
):
    response = await client.post(
        "/api/v1/agents",
        json={
            "name": "Fixed Realtime Model",
            "use_realtime": True,
            "realtime_provider": "customer-provider",
            "realtime_model": "customer-model",
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 201
    assert response.json()["realtime_provider"] == "openai"
    assert response.json()["realtime_model"] == "gpt-realtime"


@pytest.mark.asyncio
async def test_updating_legacy_realtime_agent_replaces_openai_voice(
    client: AsyncClient,
    admin_a_token: str,
    agent_a: Agent,
):
    agent_a.use_realtime = True
    agent_a.realtime_provider = "openai"
    agent_a.realtime_model = "gpt-4o-realtime-preview"
    agent_a.voice_provider = "openai"
    agent_a.voice_id = "alloy"

    response = await client.patch(
        f"/api/v1/agents/{agent_a.id}",
        json={"greeting_message": "Realtime greeting"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["realtime_model"] == "gpt-realtime"
    assert data["voice_provider"] == "elevenlabs"
    assert data["voice_id"] == "JBFqnCBsd6RMkjVDRZzb"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_agent(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    """GET /agents/{id} must return the correct agent."""
    response = await client.get(
        f"/api/v1/agents/{agent_a.id}",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(agent_a.id)
    assert data["name"] == agent_a.name


@pytest.mark.asyncio
async def test_get_agent_not_found(
    client: AsyncClient,
    admin_a_token: str,
):
    """GET /agents/{id} with a random UUID must return 404."""
    import uuid

    response = await client.get(
        f"/api/v1/agents/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_agents(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    """List must return paginated response with at least one agent."""
    response = await client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_agents_pagination(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
    company_a,
):
    """page_size=1 must return only a single item per page."""
    response = await client.get(
        "/api/v1/agents?page=1&page_size=1",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 1


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_agent(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    """PATCH /agents/{id} must apply partial updates."""
    response = await client.patch(
        f"/api/v1/agents/{agent_a.id}",
        json={"name": "Updated Agent Name"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Agent Name"


@pytest.mark.asyncio
async def test_update_agent_multiple_fields(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    """PATCH must allow updating several fields at once."""
    response = await client.patch(
        f"/api/v1/agents/{agent_a.id}",
        json={
            "greeting_message": "Hi there!",
            "system_prompt": "New prompt.",
            "language": "ar",
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["greeting_message"] == "Hi there!"
    assert data["language"] == "ar"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_agent(
    client: AsyncClient,
    admin_a_token: str,
    company_a,
):
    """DELETE /agents/{id} must respond 204 and the agent must become 404."""
    # Create a disposable agent
    create_resp = await client.post(
        "/api/v1/agents",
        json={"name": "To Delete", "language": "en"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert delete_resp.status_code == 204

    # The agent must now be gone
    get_resp = await client.get(
        f"/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Templates (public endpoint, no auth)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_agent_templates(client: AsyncClient):
    """GET /agents/templates must return exactly 3 predefined templates."""
    response = await client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    templates = response.json()
    assert len(templates) == 3
    types = {t["business_type"] for t in templates}
    assert "restaurant" in types
    assert "car_rental" in types
    assert "customer_support" in types


@pytest.mark.asyncio
async def test_agent_template_structure(client: AsyncClient):
    """Each template must contain the expected fields."""
    response = await client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    for template in response.json():
        assert "business_type" in template
        assert "name" in template
        assert "system_prompt" in template
        assert "greeting_message" in template
