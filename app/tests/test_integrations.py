import uuid
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integrations.models import Integration, IntegrationType, IntegrationStatus
from app.modules.companies.models import Company
from app.core.security import encrypt_credential


@pytest.mark.asyncio
async def test_create_integration(client: AsyncClient, admin_a_token: str):
    response = await client.post(
        "/api/v1/integrations",
        json={
            "integration_type": "erpnext",
            "name": "Test ERPNext",
            "base_url": "https://erp.example.com",
            "api_key": "test-key",
            "api_secret": "test-secret",
            "configuration": {
                "customer_doctype": "Customer",
                "request_doctype": "Booking Request",
            },
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["integration_type"] == "erpnext"
    assert data["status"] == "pending"
    # Credentials must NOT appear in the response
    assert "api_key" not in data
    assert "api_key_encrypted" not in data
    assert "api_secret_encrypted" not in data


@pytest.mark.asyncio
async def test_list_integrations(
    client: AsyncClient, admin_a_token: str, db_session: AsyncSession, company_a: Company
):
    integration = Integration(
        id=uuid.uuid4(),
        company_id=company_a.id,
        integration_type=IntegrationType.ERPNEXT,
        name="List Test Integration",
        status=IntegrationStatus.PENDING,
    )
    db_session.add(integration)
    await db_session.flush()

    response = await client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    ids = [item["id"] for item in data["items"]]
    assert str(integration.id) in ids


@pytest.mark.asyncio
async def test_operator_cannot_access_integrations(
    client: AsyncClient, operator_a_token: str
):
    response = await client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_erpnext_test_connection_success(
    client: AsyncClient,
    admin_a_token: str,
    db_session: AsyncSession,
    company_a: Company,
):
    integration = Integration(
        id=uuid.uuid4(),
        company_id=company_a.id,
        integration_type=IntegrationType.ERPNEXT,
        name="ERPNext Connection Test",
        base_url="https://erp.example.com",
        api_key_encrypted=encrypt_credential("test-key"),
        api_secret_encrypted=encrypt_credential("test-secret"),
        status=IntegrationStatus.PENDING,
    )
    db_session.add(integration)
    await db_session.flush()

    mock_result = {"success": True, "user": "Administrator"}
    with patch(
        "app.modules.integrations.providers.erpnext.client.ERPNextClient.test_connection",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            f"/api/v1/integrations/{integration.id}/test",
            headers={"Authorization": f"Bearer {admin_a_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Connection successful" in data["message"]


@pytest.mark.asyncio
async def test_erpnext_test_connection_failure(
    client: AsyncClient,
    admin_a_token: str,
    db_session: AsyncSession,
    company_a: Company,
):
    integration = Integration(
        id=uuid.uuid4(),
        company_id=company_a.id,
        integration_type=IntegrationType.ERPNEXT,
        name="ERPNext Unreachable",
        base_url="https://erp.unreachable.example.com",
        api_key_encrypted=encrypt_credential("bad-key"),
        api_secret_encrypted=encrypt_credential("bad-secret"),
        status=IntegrationStatus.PENDING,
    )
    db_session.add(integration)
    await db_session.flush()

    mock_result = {"success": False, "error": "Connection failed: Name or service not known"}
    with patch(
        "app.modules.integrations.providers.erpnext.client.ERPNextClient.test_connection",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            f"/api/v1/integrations/{integration.id}/test",
            headers={"Authorization": f"Bearer {admin_a_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_connect_integration(
    client: AsyncClient,
    admin_a_token: str,
    db_session: AsyncSession,
    company_a: Company,
):
    integration = Integration(
        id=uuid.uuid4(),
        company_id=company_a.id,
        integration_type=IntegrationType.ERPNEXT,
        name="ERPNext Connect Test",
        status=IntegrationStatus.PENDING,
    )
    db_session.add(integration)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/integrations/{integration.id}/connect",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "connected"


@pytest.mark.asyncio
async def test_disconnect_integration(
    client: AsyncClient,
    admin_a_token: str,
    db_session: AsyncSession,
    company_a: Company,
):
    integration = Integration(
        id=uuid.uuid4(),
        company_id=company_a.id,
        integration_type=IntegrationType.ERPNEXT,
        name="ERPNext Disconnect Test",
        status=IntegrationStatus.CONNECTED,
    )
    db_session.add(integration)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/integrations/{integration.id}/disconnect",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"


@pytest.mark.asyncio
async def test_company_b_cannot_access_company_a_integration(
    client: AsyncClient,
    admin_b_token: str,
    db_session: AsyncSession,
    company_a: Company,
):
    integration = Integration(
        id=uuid.uuid4(),
        company_id=company_a.id,
        integration_type=IntegrationType.ERPNEXT,
        name="Company A Private Integration",
        status=IntegrationStatus.CONNECTED,
    )
    db_session.add(integration)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/integrations/{integration.id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code == 404
