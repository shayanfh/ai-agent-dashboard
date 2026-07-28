"""
Tenant isolation tests.

Verifies that a user belonging to Company B cannot read or operate on
resources that belong to Company A, and vice-versa.
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import Agent, AgentStatus
from app.modules.calls.models import Call, CallStatus
from app.modules.companies.models import Company


@pytest.mark.asyncio
async def test_admin_b_cannot_list_company_a_agents(
    client: AsyncClient,
    agent_a: Agent,
    admin_b_token: str,
):
    """Company B admin must not see Company A agents in the list."""
    response = await client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    agent_ids = [item["id"] for item in items]
    assert str(agent_a.id) not in agent_ids


@pytest.mark.asyncio
async def test_admin_b_cannot_get_company_a_agent(
    client: AsyncClient,
    agent_a: Agent,
    admin_b_token: str,
):
    """Company B admin must receive 404 when accessing a Company A agent."""
    response = await client.get(
        f"/api/v1/agents/{agent_a.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_b_cannot_update_company_a_agent(
    client: AsyncClient,
    agent_a: Agent,
    admin_b_token: str,
):
    """Company B admin must not be able to mutate Company A's agent."""
    response = await client.patch(
        f"/api/v1/agents/{agent_a.id}",
        json={"name": "Hijacked"},
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    # Either 403 (permission) or 404 (hidden due to tenant filter) is correct.
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_admin_b_cannot_delete_company_a_agent(
    client: AsyncClient,
    agent_a: Agent,
    admin_b_token: str,
):
    """Company B admin must not be able to delete Company A's agent."""
    response = await client.delete(
        f"/api/v1/agents/{agent_a.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_admin_b_cannot_get_company_a_call(
    client: AsyncClient,
    call_a: Call,
    admin_b_token: str,
):
    """Company B admin must receive 404 when accessing Company A's call."""
    response = await client.get(
        f"/api/v1/calls/{call_a.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_operator_a_call_list_scoped_to_company_a(
    client: AsyncClient,
    call_a: Call,
    operator_a_token: str,
):
    """Operator A's call list must not be empty (their company's calls are visible)."""
    response = await client.get(
        "/api/v1/calls",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # The call belonging to Company A must appear for Operator A.
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_company_b_call_not_in_company_a_operator_list(
    client: AsyncClient,
    operator_a_token: str,
    company_b: Company,
    db_session: AsyncSession,
):
    """
    A call that belongs to Company B must never appear in
    an Operator A listing.
    """
    from app.modules.agents.models import Agent as AgentModel, AgentStatus

    # Create a minimal Company-B agent so we can attach the call
    agent_b = AgentModel(
        id=uuid.uuid4(),
        company_id=company_b.id,
        name="Agent B",
        language="en",
        status=AgentStatus.ACTIVE,
    )
    db_session.add(agent_b)

    call_b = Call(
        id=uuid.uuid4(),
        company_id=company_b.id,
        agent_id=agent_b.id,
        caller_number="+96899999999",
        status=CallStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call_b)
    await db_session.flush()

    response = await client.get(
        "/api/v1/calls",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 200
    call_ids = [item["id"] for item in response.json()["items"]]
    assert str(call_b.id) not in call_ids


@pytest.mark.asyncio
async def test_company_a_cannot_reference_company_b_agent(
    client: AsyncClient,
    admin_a_token: str,
    company_b: Company,
    db_session: AsyncSession,
):
    agent_b = Agent(
        id=uuid.uuid4(),
        company_id=company_b.id,
        name="Company B Agent",
        language="en",
        status=AgentStatus.ACTIVE,
    )
    db_session.add(agent_b)
    await db_session.flush()

    headers = {"Authorization": f"Bearer {admin_a_token}"}
    requests = [
        (
            "/api/v1/calls",
            {
                "agent_id": str(agent_b.id),
                "caller_number": "+96890000001",
            },
        ),
        (
            "/api/v1/phone-numbers",
            {
                "phone_number": "+96890000002",
                "agent_id": str(agent_b.id),
            },
        ),
        (
            "/api/v1/requests",
            {
                "agent_id": str(agent_b.id),
                "request_type": "general_request",
            },
        ),
        (
            "/api/v1/knowledge-base/items",
            {
                "agent_id": str(agent_b.id),
                "question": "Cross-tenant question",
                "answer": "Must be rejected",
            },
        ),
        (
            "/api/v1/knowledge-base/documents",
            {
                "agent_id": str(agent_b.id),
                "file_name": "cross-tenant.txt",
                "file_type": "txt",
            },
        ),
    ]

    for url, payload in requests:
        response = await client.post(url, json=payload, headers=headers)
        assert response.status_code == 404, (url, response.text)


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(client: AsyncClient):
    """Any request without a token must be rejected (401/403)."""
    response = await client.get("/api/v1/agents")
    assert response.status_code in (401, 403)
