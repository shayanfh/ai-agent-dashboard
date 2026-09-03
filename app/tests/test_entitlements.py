import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.agents.test_calls import WebTestCallService
from app.modules.billing.models import Plan, Subscription, SubscriptionStatus
from app.modules.calls.models import Call, CallStatus
from app.modules.integrations.models import Integration, IntegrationStatus, IntegrationType


async def _subscribe(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    starts: timedelta = timedelta(days=-1),
    ends: timedelta = timedelta(days=29),
    monthly_minutes: int | None = 100,
    max_agents: int | None = 10,
    max_integrations: int | None = 10,
    plan_active: bool = True,
) -> Subscription:
    plan = Plan(
        name=f"Entitlement {uuid.uuid4().hex[:8]}",
        slug=f"entitlement-{uuid.uuid4().hex}",
        monthly_minutes=monthly_minutes,
        max_agents=max_agents,
        max_integrations=max_integrations,
        is_active=plan_active,
    )
    now = datetime.now(timezone.utc)
    subscription = Subscription(
        company_id=company_id,
        plan=plan,
        status=status,
        current_period_start=now + starts,
        current_period_end=now + ends,
    )
    db.add(subscription)
    await db.flush()
    return subscription


@pytest.mark.asyncio
async def test_agent_creation_requires_subscription(client, admin_a_token):
    response = await client.post(
        "/api/v1/agents",
        json={"name": "Blocked"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SUBSCRIPTION_REQUIRED"


@pytest.mark.asyncio
async def test_agent_limit_returns_frontend_details(
    client, db_session, company_a, agent_a, admin_a_token
):
    await _subscribe(db_session, company_a.id, max_agents=1)

    response = await client.post(
        "/api/v1/agents",
        json={"name": "Over limit"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "PLAN_LIMIT_REACHED",
        "message": "The plan limit for agents has been reached.",
        "details": {"resource": "agents", "used": 1, "limit": 1},
    }


@pytest.mark.asyncio
async def test_integration_limit_is_enforced(
    client, db_session, company_a, admin_a_token
):
    await _subscribe(db_session, company_a.id, max_integrations=1)
    db_session.add(
        Integration(
            company_id=company_a.id,
            integration_type=IntegrationType.ERPNEXT,
            name="Existing",
            status=IntegrationStatus.PENDING,
        )
    )
    await db_session.flush()

    response = await client.post(
        "/api/v1/integrations",
        json={"integration_type": "erpnext", "name": "Over limit"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["resource"] == "integrations"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subscription_kwargs", "expected_code"),
    [
        ({"status": SubscriptionStatus.PAST_DUE}, "SUBSCRIPTION_INACTIVE"),
        ({"ends": timedelta(seconds=-1)}, "SUBSCRIPTION_PERIOD_INACTIVE"),
        ({"plan_active": False}, "PLAN_UNAVAILABLE"),
    ],
)
async def test_subscription_state_blocks_paid_features(
    client,
    db_session,
    company_a,
    admin_a_token,
    subscription_kwargs,
    expected_code,
):
    await _subscribe(db_session, company_a.id, **subscription_kwargs)

    response = await client.post(
        "/api/v1/agents",
        json={"name": "Blocked"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.asyncio
async def test_browser_test_call_uses_monthly_minute_allowance(
    client, db_session, company_a, agent_a, admin_a_token, monkeypatch
):
    await _subscribe(db_session, company_a.id, monthly_minutes=1)
    db_session.add(
        Call(
            company_id=company_a.id,
            agent_id=agent_a.id,
            status=CallStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            duration_seconds=60,
        )
    )
    await db_session.flush()
    monkeypatch.setattr(settings, "LIVEKIT_URL", "wss://livekit.example.com")
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "key")
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "secret")
    monkeypatch.setattr(settings, "LIVEKIT_AGENT_NAME", "agent")
    monkeypatch.setattr(
        WebTestCallService,
        "_build_access_token",
        staticmethod(lambda **_: "token"),
    )

    response = await client.post(
        f"/api/v1/agents/{agent_a.id}/test-calls",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "MONTHLY_MINUTES_EXHAUSTED"
    assert error["details"]["limit_seconds"] == 60


@pytest.mark.asyncio
async def test_inbound_resolution_requires_subscription(client, phone_a):
    response = await client.get(
        "/api/v1/internal/voice/resolve-agent",
        params={"phone_number": phone_a.phone_number},
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SUBSCRIPTION_REQUIRED"


@pytest.mark.asyncio
async def test_outbound_campaign_creation_requires_subscription(
    client, phone_a, admin_a_token
):
    response = await client.post(
        "/api/v1/outbound-campaigns",
        json={
            "name": "Blocked campaign",
            "campaign_type": "voice_broadcast",
            "phone_number_id": str(phone_a.id),
            "message_text": "Hello",
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SUBSCRIPTION_REQUIRED"
