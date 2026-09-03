import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as fastapi_app
from app.modules.billing.models import (
    Invoice,
    InvoiceStatus,
    Payment,
    Plan,
    StripeEvent,
    Subscription,
    SubscriptionStatus,
)
from app.modules.billing.stripe_gateway import get_stripe_gateway
from app.modules.companies.models import Company


class FakeStripeGateway:
    def __init__(self) -> None:
        self.event = None
        self.checkout_calls: list[dict] = []
        self.portal_calls: list[dict] = []
        self.cancellation_calls: list[dict] = []

    async def create_customer(self, **kwargs):
        return {"id": "cus_test_company"}

    async def create_checkout_session(self, **kwargs):
        self.checkout_calls.append(kwargs)
        return {
            "id": "cs_test_checkout",
            "url": "https://checkout.stripe.test/cs_test_checkout",
        }

    async def create_portal_session(self, **kwargs):
        self.portal_calls.append(kwargs)
        return {"url": "https://billing.stripe.test/session"}

    async def update_subscription_cancellation(self, **kwargs):
        self.cancellation_calls.append(kwargs)

    def construct_webhook_event(self, payload: bytes, signature: str):
        assert signature == "test-signature"
        assert json.loads(payload)
        return self.event


async def create_subscription(db: AsyncSession, company: Company) -> Subscription:
    plan = await db.scalar(select(Plan).where(Plan.slug == "trial"))
    now = datetime.now(timezone.utc)
    subscription = Subscription(
        company_id=company.id,
        plan_id=plan.id,
        status=SubscriptionStatus.TRIAL,
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=13),
    )
    db.add(subscription)
    await db.flush()
    return subscription


@pytest.mark.asyncio
async def test_checkout_uses_server_side_price_and_creates_pending_invoice(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    admin_a_token: str,
):
    subscription = await create_subscription(db_session, company_a)
    plan = await db_session.scalar(select(Plan).where(Plan.slug == "starter"))
    plan.price_monthly_minor = 2500
    plan.currency = "USD"
    plan.stripe_price_id = "price_starter_test"
    await db_session.flush()
    gateway = FakeStripeGateway()
    fastapi_app.dependency_overrides[get_stripe_gateway] = lambda: gateway

    response = await client.post(
        "/api/v1/billing/stripe/checkout-session",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={"plan_id": str(plan.id)},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "session_id": "cs_test_checkout",
        "checkout_url": "https://checkout.stripe.test/cs_test_checkout",
    }
    assert gateway.checkout_calls[0]["price_id"] == "price_starter_test"
    assert gateway.checkout_calls[0]["customer_id"] == "cus_test_company"
    await db_session.refresh(company_a)
    await db_session.refresh(subscription)
    assert company_a.stripe_customer_id == "cus_test_company"
    assert subscription.pending_plan_id == plan.id
    invoice = await db_session.scalar(
        select(Invoice).where(Invoice.subscription_id == subscription.id)
    )
    assert invoice.amount_due_minor == 2500
    assert invoice.stripe_checkout_session_id == "cs_test_checkout"


@pytest.mark.asyncio
async def test_checkout_webhook_activates_plan_and_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    admin_a_token: str,
):
    subscription = await create_subscription(db_session, company_a)
    plan = await db_session.scalar(select(Plan).where(Plan.slug == "starter"))
    plan.price_monthly_minor = 2500
    plan.currency = "USD"
    plan.stripe_price_id = "price_starter_webhook"
    await db_session.flush()
    gateway = FakeStripeGateway()
    fastapi_app.dependency_overrides[get_stripe_gateway] = lambda: gateway

    checkout = await client.post(
        "/api/v1/billing/stripe/checkout-session",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={"plan_id": str(plan.id)},
    )
    assert checkout.status_code == 200, checkout.text
    invoice = await db_session.scalar(
        select(Invoice).where(Invoice.subscription_id == subscription.id)
    )
    gateway.event = {
        "id": "evt_checkout_paid",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_checkout",
                "payment_status": "paid",
                "amount_total": 2500,
                "currency": "usd",
                "customer": "cus_test_company",
                "subscription": "sub_test_company",
                "invoice": "in_test_initial",
                "metadata": {
                    "company_id": str(company_a.id),
                    "plan_id": str(plan.id),
                    "local_invoice_id": str(invoice.id),
                },
            }
        },
    }

    first = await client.post(
        "/api/v1/billing/stripe/webhook",
        content=b'{"delivery": 1}',
        headers={"Stripe-Signature": "test-signature"},
    )
    second = await client.post(
        "/api/v1/billing/stripe/webhook",
        content=b'{"delivery": 2}',
        headers={"Stripe-Signature": "test-signature"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    await db_session.refresh(subscription)
    await db_session.refresh(invoice)
    assert subscription.plan_id == plan.id
    assert subscription.pending_plan_id is None
    assert subscription.stripe_subscription_id == "sub_test_company"
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.stripe_invoice_id == "in_test_initial"
    assert await db_session.scalar(select(func.count(Payment.id))) == 1
    assert await db_session.scalar(select(func.count(StripeEvent.id))) == 1

    now = int(datetime.now(timezone.utc).timestamp())
    gateway.event = {
        "id": "evt_renewal_paid",
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "in_test_renewal",
                "subscription": "sub_test_company",
                "amount_paid": 2500,
                "currency": "usd",
                "status_transitions": {"paid_at": now},
                "lines": {
                    "data": [
                        {"period": {"start": now, "end": now + 30 * 86400}}
                    ]
                },
            }
        },
    }
    renewal = await client.post(
        "/api/v1/billing/stripe/webhook",
        content=b'{"delivery": 3}',
        headers={"Stripe-Signature": "test-signature"},
    )
    assert renewal.status_code == 200, renewal.text
    assert await db_session.scalar(select(func.count(Invoice.id))) == 2
    assert await db_session.scalar(select(func.count(Payment.id))) == 2


@pytest.mark.asyncio
async def test_portal_and_cancellation_use_existing_stripe_customer(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    admin_a_token: str,
):
    subscription = await create_subscription(db_session, company_a)
    company_a.stripe_customer_id = "cus_portal"
    subscription.stripe_subscription_id = "sub_portal"
    await db_session.flush()
    gateway = FakeStripeGateway()
    fastapi_app.dependency_overrides[get_stripe_gateway] = lambda: gateway
    headers = {"Authorization": f"Bearer {admin_a_token}"}

    portal = await client.post("/api/v1/billing/stripe/portal-session", headers=headers)
    cancellation = await client.post(
        "/api/v1/billing/subscription/cancel", headers=headers
    )

    assert portal.status_code == 200, portal.text
    assert portal.json()["portal_url"] == "https://billing.stripe.test/session"
    assert gateway.portal_calls[0]["customer_id"] == "cus_portal"
    assert cancellation.status_code == 200, cancellation.text
    assert gateway.cancellation_calls == [
        {"subscription_id": "sub_portal", "cancel_at_period_end": True}
    ]
