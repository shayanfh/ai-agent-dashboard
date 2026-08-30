from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import Agent
from app.modules.billing.models import Invoice, InvoiceStatus, Plan, Subscription, SubscriptionStatus
from app.modules.calls.models import Call, CallStatus
from app.modules.companies.models import Company


async def create_subscription(
    db: AsyncSession, company: Company, plan_slug: str = "trial"
) -> tuple[Subscription, Plan]:
    plan = await db.scalar(select(Plan).where(Plan.slug == plan_slug))
    now = datetime.now(timezone.utc)
    subscription = Subscription(
        company_id=company.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now - timedelta(days=5),
        current_period_end=now + timedelta(days=25),
    )
    db.add(subscription)
    await db.flush()
    return subscription, plan


@pytest.mark.asyncio
async def test_company_reads_subscription_and_current_period_usage(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    agent_a: Agent,
    admin_a_token: str,
):
    await create_subscription(db_session, company_a)
    db_session.add(
        Call(
            company_id=company_a.id,
            agent_id=agent_a.id,
            status=CallStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            duration_seconds=750,
        )
    )
    await db_session.flush()
    headers = {"Authorization": f"Bearer {admin_a_token}"}

    subscription = await client.get("/api/v1/billing/subscription", headers=headers)
    usage = await client.get("/api/v1/billing/usage", headers=headers)

    assert subscription.status_code == 200
    assert subscription.json()["plan"]["slug"] == "trial"
    assert usage.status_code == 200
    assert usage.json()["minutes_used"] == 12.5
    assert usage.json()["minutes_remaining"] == 187.5


@pytest.mark.asyncio
async def test_invoice_list_is_tenant_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    company_b: Company,
    admin_a_token: str,
):
    for company, number in ((company_a, "INV-A"), (company_b, "INV-B")):
        db_session.add(
            Invoice(
                company_id=company.id,
                number=number,
                status=InvoiceStatus.OPEN,
                currency="USD",
                subtotal_minor=1000,
                tax_minor=0,
                total_minor=1000,
                amount_paid_minor=0,
                amount_due_minor=1000,
            )
        )
    await db_session.flush()

    response = await client.get(
        "/api/v1/billing/invoices",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["number"] == "INV-A"


@pytest.mark.asyncio
async def test_paid_plan_change_activates_only_after_full_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    admin_a_token: str,
    super_admin_token: str,
):
    subscription, _ = await create_subscription(db_session, company_a)
    starter = await db_session.scalar(select(Plan).where(Plan.slug == "starter"))
    starter.price_monthly_minor = 2500
    starter.currency = "USD"
    await db_session.flush()

    change = await client.post(
        "/api/v1/billing/subscription/change",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={"plan_id": str(starter.id)},
    )
    assert change.status_code == 200, change.text
    assert change.json()["requires_payment"] is True
    assert change.json()["subscription"]["plan"]["slug"] == "trial"
    assert change.json()["subscription"]["pending_plan"]["slug"] == "starter"
    invoice_id = change.json()["invoice"]["id"]

    partial = await client.post(
        f"/api/v1/admin/billing/invoices/{invoice_id}/payments",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={"amount_minor": 1000, "external_reference": "pay-partial"},
    )
    assert partial.status_code == 201, partial.text
    await db_session.refresh(subscription)
    assert subscription.plan_id != starter.id

    final = await client.post(
        f"/api/v1/admin/billing/invoices/{invoice_id}/payments",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={"amount_minor": 1500, "external_reference": "pay-final"},
    )
    assert final.status_code == 201, final.text
    await db_session.refresh(subscription)
    assert subscription.plan_id == starter.id
    assert subscription.pending_plan_id is None
    invoice = await db_session.get(Invoice, invoice_id)
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.amount_due_minor == 0


@pytest.mark.asyncio
async def test_company_can_schedule_cancellation_and_resume(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    admin_a_token: str,
):
    await create_subscription(db_session, company_a)
    headers = {"Authorization": f"Bearer {admin_a_token}"}

    cancelled = await client.post("/api/v1/billing/subscription/cancel", headers=headers)
    resumed = await client.post("/api/v1/billing/subscription/resume", headers=headers)

    assert cancelled.status_code == 200
    assert cancelled.json()["cancel_at_period_end"] is True
    assert resumed.status_code == 200
    assert resumed.json()["cancel_at_period_end"] is False
    assert resumed.json()["cancelled_at"] is None


@pytest.mark.asyncio
async def test_super_admin_can_create_plan_and_manual_invoice(
    client: AsyncClient,
    company_a: Company,
    super_admin_token: str,
):
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    plan = await client.post(
        "/api/v1/admin/billing/plans",
        headers=headers,
        json={
            "name": "Business",
            "slug": "business",
            "monthly_minutes": 5000,
            "max_agents": 20,
            "max_integrations": 20,
            "price_monthly_minor": 9900,
            "currency": "usd",
        },
    )
    invoice = await client.post(
        "/api/v1/admin/billing/invoices",
        headers=headers,
        json={
            "company_id": str(company_a.id),
            "amount_minor": 5000,
            "tax_minor": 500,
            "currency": "usd",
            "description": "Manual service charge",
        },
    )

    assert plan.status_code == 201, plan.text
    assert plan.json()["currency"] == "USD"
    assert invoice.status_code == 201, invoice.text
    assert invoice.json()["total_minor"] == 5500
    assert invoice.json()["amount_due_minor"] == 5500


@pytest.mark.asyncio
async def test_super_admin_can_delete_unused_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin_token: str,
):
    plan = Plan(
        name="Temporary",
        slug="temporary-delete-test",
        monthly_minutes=100,
        max_agents=1,
        max_integrations=1,
    )
    db_session.add(plan)
    await db_session.flush()

    response = await client.delete(
        f"/api/v1/admin/billing/plans/{plan.id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )

    assert response.status_code == 204, response.text
    assert await db_session.get(Plan, plan.id) is None


@pytest.mark.asyncio
async def test_plan_in_use_cannot_be_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    super_admin_token: str,
):
    _, plan = await create_subscription(db_session, company_a)

    response = await client.delete(
        f"/api/v1/admin/billing/plans/{plan.id}",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_company_admin_cannot_delete_plan(
    client: AsyncClient,
    admin_a_token: str,
):
    response = await client.delete(
        "/api/v1/admin/billing/plans/00000000-0000-0000-0000-000000000102",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 403
