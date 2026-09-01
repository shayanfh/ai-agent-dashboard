from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.agents.models import Agent
from app.modules.agents.test_calls import WebTestCallService
from app.modules.billing.models import Plan, Subscription, SubscriptionStatus
from app.modules.calls.models import Call, CallSource, CallStatus
from app.modules.companies.models import Company


@pytest.fixture
def configured_livekit(monkeypatch):
    monkeypatch.setattr(settings, "LIVEKIT_URL", "wss://livekit.example.com")
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "test-secret")
    monkeypatch.setattr(settings, "LIVEKIT_AGENT_NAME", "test-agent")
    monkeypatch.setattr(
        WebTestCallService,
        "_build_access_token",
        staticmethod(lambda **_: "signed-test-token"),
    )


@pytest.mark.asyncio
async def test_company_creates_browser_test_call_session(
    client: AsyncClient,
    db_session: AsyncSession,
    agent_a: Agent,
    admin_a_token: str,
    configured_livekit,
):
    response = await client.post(
        f"/api/v1/agents/{agent_a.id}/test-calls",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == str(agent_a.id)
    assert data["livekit_url"] == "wss://livekit.example.com"
    assert data["access_token"] == "signed-test-token"
    assert data["max_duration_seconds"] == 600
    assert data["room_name"].startswith("web-test-")

    call = await db_session.get(Call, data["call_id"])
    assert call is not None
    assert call.source == CallSource.WEB_TEST
    assert call.status == CallStatus.INITIATED
    assert call.metadata_["participant_identity"] == data["participant_identity"]


@pytest.mark.asyncio
async def test_company_cannot_test_another_tenants_agent(
    client: AsyncClient,
    agent_a: Agent,
    admin_b_token: str,
    configured_livekit,
):
    response = await client.post(
        f"/api/v1/agents/{agent_a.id}/test-calls",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_test_usage_is_reported_separately(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    agent_a: Agent,
    admin_a_token: str,
):
    plan = await db_session.scalar(select(Plan).where(Plan.slug == "trial"))
    now = datetime.now(timezone.utc)
    db_session.add(
        Subscription(
            company_id=company_a.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=29),
        )
    )
    db_session.add_all(
        [
            Call(
                company_id=company_a.id,
                agent_id=agent_a.id,
                source=CallSource.WEB_TEST,
                status=CallStatus.COMPLETED,
                started_at=now,
                duration_seconds=90,
            ),
            Call(
                company_id=company_a.id,
                agent_id=agent_a.id,
                source=CallSource.TELEPHONY,
                status=CallStatus.COMPLETED,
                started_at=now,
                duration_seconds=120,
            ),
        ]
    )
    await db_session.flush()
    headers = {"Authorization": f"Bearer {admin_a_token}"}

    test_usage = await client.get("/api/v1/agents/test-calls/usage", headers=headers)
    billing_usage = await client.get("/api/v1/billing/usage", headers=headers)

    assert test_usage.status_code == 200
    assert test_usage.json()["duration_seconds"] == 90
    assert test_usage.json()["minutes_used"] == 1.5
    assert test_usage.json()["max_duration_seconds_per_call"] == 600
    assert billing_usage.status_code == 200
    assert billing_usage.json()["minutes_used"] == 3.5
    assert billing_usage.json()["telephony_minutes_used"] == 2.0
    assert billing_usage.json()["web_test_minutes_used"] == 1.5


@pytest.mark.asyncio
async def test_voice_agent_resolves_web_test_context_and_transfer_is_blocked(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    agent_a: Agent,
):
    call = Call(
        company_id=company_a.id,
        agent_id=agent_a.id,
        source=CallSource.WEB_TEST,
        status=CallStatus.INITIATED,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call)
    await db_session.flush()
    internal_headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY}

    resolved = await client.get(
        "/api/v1/internal/voice/resolve-agent-by-id",
        params={
            "agent_id": str(agent_a.id),
            "company_id": str(company_a.id),
            "call_id": str(call.id),
        },
        headers=internal_headers,
    )
    transfer = await client.post(
        f"/api/v1/internal/voice/calls/{call.id}/transfer-target",
        json={"target": "100"},
        headers=internal_headers,
    )

    assert resolved.status_code == 200
    assert resolved.json()["agent_id"] == str(agent_a.id)
    await db_session.refresh(call)
    assert call.status == CallStatus.IN_PROGRESS
    assert call.answered_at is not None
    assert transfer.status_code == 409
    assert transfer.json()["error"]["message"] == (
        "Transfers are disabled for browser test calls"
    )


@pytest.mark.asyncio
async def test_web_test_persisted_duration_is_capped_at_ten_minutes(
    client: AsyncClient,
    db_session: AsyncSession,
    company_a: Company,
    agent_a: Agent,
):
    call = Call(
        company_id=company_a.id,
        agent_id=agent_a.id,
        source=CallSource.WEB_TEST,
        status=CallStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/internal/voice/calls/{call.id}/complete",
        json={"outcome": "no_action", "duration_seconds": 999},
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
    )

    assert response.status_code == 200
    await db_session.refresh(call)
    assert call.duration_seconds == 600
