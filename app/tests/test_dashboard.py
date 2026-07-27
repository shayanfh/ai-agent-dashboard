import pytest
from httpx import AsyncClient
from app.modules.calls.models import Call


@pytest.mark.asyncio
async def test_dashboard_summary_returns_all_fields(
    client: AsyncClient, call_a: Call, admin_a_token: str
):
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    required_fields = [
        "total_calls",
        "calls_today",
        "answered_calls",
        "missed_calls",
        "failed_calls",
        "requests_created",
        "transferred_calls",
        "total_minutes_used",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_dashboard_summary_counts_company_calls(
    client: AsyncClient, call_a: Call, admin_a_token: str
):
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_calls"] >= 1


@pytest.mark.asyncio
async def test_dashboard_summary_isolated_by_company(
    client: AsyncClient,
    call_a: Call,
    admin_b_token: str,
):
    """Company B should not count Company A's calls."""
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Company B has no calls seeded, total should be 0
    assert data["total_calls"] == 0


@pytest.mark.asyncio
async def test_dashboard_call_volume(client: AsyncClient, call_a: Call, admin_a_token: str):
    response = await client.get(
        "/api/v1/dashboard/call-volume?days=7",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert data["period_days"] == 7
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_dashboard_call_volume_custom_days(
    client: AsyncClient, admin_a_token: str
):
    response = await client.get(
        "/api/v1/dashboard/call-volume?days=30",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    assert response.json()["period_days"] == 30


@pytest.mark.asyncio
async def test_dashboard_outcomes(client: AsyncClient, admin_a_token: str):
    response = await client.get(
        "/api/v1/dashboard/outcomes",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/dashboard/summary")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_view_dashboard(
    client: AsyncClient, call_a: Call, operator_a_token: str
):
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {operator_a_token}"},
    )
    assert response.status_code == 200
