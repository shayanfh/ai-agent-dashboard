from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import Plan, Subscription, SubscriptionStatus
from app.modules.calls.models import Call, CallStatus
from app.modules.companies.models import Company
from app.modules.integrations.models import Integration, IntegrationStatus, IntegrationType


@pytest.mark.asyncio
async def test_super_admin_sees_client_usage_and_resource_counts(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    agent_a,
    super_admin_token: str,
):
    starter = await db_session.scalar(select(Plan).where(Plan.slug == "starter"))
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    db_session.add_all(
        [
            Subscription(
                company_id=company_a.id,
                plan_id=starter.id,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=start,
                current_period_end=AdminPeriod.next_month(start),
            ),
            Call(
                company_id=company_a.id,
                agent_id=agent_a.id,
                caller_number="+96890000001",
                status=CallStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                duration_seconds=750,
            ),
            Integration(
                company_id=company_a.id,
                integration_type=IntegrationType.WEBHOOK,
                name="CRM webhook",
                status=IntegrationStatus.CONNECTED,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/admin/clients",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )

    assert response.status_code == 200
    item = next(row for row in response.json()["items"] if row["id"] == str(company_a.id))
    assert item["agent_count"] == 1
    assert item["integration_count"] == 1
    assert item["package"]["slug"] == "starter"
    assert item["monthly_minutes_used"] == 12.5
    assert item["monthly_minutes_remaining"] == 487.5


@pytest.mark.asyncio
async def test_company_admin_cannot_access_super_admin_client_report(
    client: AsyncClient,
    admin_a_token: str,
):
    response = await client.get(
        "/api/v1/admin/clients",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_super_admin_can_assign_a_package(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    super_admin_token: str,
):
    starter = await db_session.scalar(select(Plan).where(Plan.slug == "starter"))
    response = await client.patch(
        f"/api/v1/admin/clients/{company_a.id}/subscription",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={"plan_id": str(starter.id), "status": "active"},
    )

    assert response.status_code == 200
    assert response.json()["package"]["slug"] == "starter"
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.company_id == company_a.id)
    )
    assert subscription.plan_id == starter.id


class AdminPeriod:
    @staticmethod
    def next_month(value: datetime) -> datetime:
        if value.month == 12:
            return value.replace(year=value.year + 1, month=1)
        return value.replace(month=value.month + 1)

