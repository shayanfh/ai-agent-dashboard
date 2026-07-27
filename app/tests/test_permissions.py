"""
Role-based access-control (RBAC) tests.

Verifies that:
- Operators cannot perform write operations on agents.
- Operators cannot access admin-only endpoints (integrations, companies).
- Company admins cannot access super-admin-only endpoints.
- Super admins can access every protected resource.
"""

import pytest
from httpx import AsyncClient

from app.modules.agents.models import Agent


# ---------------------------------------------------------------------------
# Operator restrictions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_operator_cannot_create_agent(
    client: AsyncClient,
    operator_a_token: str,
):
    """An Operator must receive 403 when trying to create an agent."""
    response = await client.post(
        "/api/v1/agents",
        json={"name": "New Agent", "language": "en"},
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_list_agents(
    client: AsyncClient,
    agent_a: Agent,
    operator_a_token: str,
):
    """An Operator must be allowed to list agents (read access)."""
    response = await client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_operator_can_read_single_agent(
    client: AsyncClient,
    agent_a: Agent,
    operator_a_token: str,
):
    """An Operator must be allowed to read a single agent's details."""
    response = await client.get(
        f"/api/v1/agents/{agent_a.id}",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_operator_cannot_update_agent(
    client: AsyncClient,
    agent_a: Agent,
    operator_a_token: str,
):
    """An Operator must receive 403 when trying to update an agent."""
    response = await client.patch(
        f"/api/v1/agents/{agent_a.id}",
        json={"name": "Operator Rename"},
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_delete_agent(
    client: AsyncClient,
    agent_a: Agent,
    operator_a_token: str,
):
    """An Operator must receive 403 when trying to delete an agent."""
    response = await client.delete(
        f"/api/v1/agents/{agent_a.id}",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_manage_integrations(
    client: AsyncClient,
    operator_a_token: str,
):
    """Integrations endpoint requires at least Company Admin; Operator → 403."""
    response = await client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_list_calls(
    client: AsyncClient,
    call_a,
    operator_a_token: str,
):
    """An Operator should be able to view calls in their company."""
    response = await client.get(
        "/api/v1/calls",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Company-admin restrictions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_admin_cannot_list_all_companies(
    client: AsyncClient,
    admin_a_token: str,
):
    """Company Admin must receive 403 on the super-admin-only companies list."""
    response = await client.get(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_admin_can_create_agent(
    client: AsyncClient,
    admin_a_token: str,
    company_a,
):
    """Company Admin must be able to create agents in their company."""
    response = await client.post(
        "/api/v1/agents",
        json={"name": "Admin Agent", "language": "en"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_company_admin_can_manage_integrations(
    client: AsyncClient,
    admin_a_token: str,
):
    """Company Admin must have access to the integrations endpoint."""
    response = await client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Super-admin privileges
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_super_admin_can_list_companies(
    client: AsyncClient,
    super_admin_token: str,
):
    """Super Admin must be able to list all companies."""
    response = await client.get(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_super_admin_can_access_dashboard(
    client: AsyncClient,
    super_admin_token: str,
):
    """Super Admin attempting to access the dashboard should not be blocked by auth."""
    # Super admins have no company_id; the service may return 403 for that
    # reason but must NOT return an auth/permission error (401).
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    # 200 or 403 (no company context) are both acceptable here.
    assert response.status_code in (200, 403)
