import uuid
from typing import ClassVar

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.agents.models import Agent
from app.modules.onboarding.models import (
    TelephonyConnection,
    TelephonyConnectionStatus,
)
from app.modules.phone_connections.providers import (
    LiveKitProvisioner,
    LiveKitResources,
)
from app.modules.phone_numbers.models import ConnectionStatus, PhoneNumber


class FakeLiveKitProvisioner:
    deleted: ClassVar[list[tuple[str | None, str | None]]] = []

    async def provision(self, **kwargs) -> LiveKitResources:
        return LiveKitResources("ST_test_trunk", "SDR_test_dispatch")

    async def exists(self, trunk_id: str) -> bool:
        return trunk_id == "ST_test_trunk"

    async def delete(self, trunk_id, dispatch_rule_id) -> None:
        self.deleted.append((trunk_id, dispatch_rule_id))


class FakeTwilioClient:
    calls: ClassVar[list[tuple]] = []

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token

    async def provision(self, **kwargs) -> str:
        self.calls.append((self.account_sid, self.auth_token, kwargs))
        return "TK0123456789abcdef0123456789abcdef"

    async def delete(self, trunk_sid: str) -> None:
        return None


@pytest.fixture(autouse=True)
def fake_livekit(monkeypatch):
    FakeLiveKitProvisioner.deleted.clear()
    monkeypatch.setattr(
        "app.modules.phone_connections.service.LiveKitProvisioner",
        FakeLiveKitProvisioner,
    )
    monkeypatch.setattr(settings, "LIVEKIT_SIP_ENDPOINT", "test.sip.livekit.cloud")
    FakeTwilioClient.calls.clear()
    monkeypatch.setattr(
        "app.modules.phone_connections.service.TwilioElasticSipClient",
        FakeTwilioClient,
    )


class FakeInboundTrunk:
    def __init__(self, trunk_id: str, numbers: list[str], metadata: str) -> None:
        self.sip_trunk_id = trunk_id
        self.numbers = numbers
        self.metadata = metadata
        self.name = trunk_id


class FakeSipClient:
    def __init__(self, items: list[FakeInboundTrunk]) -> None:
        self.items = items
        self.deleted: list[str] = []

    async def list_sip_inbound_trunk(self, request):
        return type("Result", (), {"items": self.items})()

    async def delete_sip_trunk(self, request):
        self.deleted.append(request.sip_trunk_id)


@pytest.mark.asyncio
async def test_stale_trunk_for_same_connection_is_replaced():
    connection_id = str(uuid.uuid4())
    sip = FakeSipClient(
        [
            FakeInboundTrunk("ST_other", ["+19990000000"], "{}"),
            FakeInboundTrunk(
                "ST_stale",
                ["+19714361744"],
                f'{{"connection_id": "{connection_id}"}}',
            ),
        ]
    )
    await LiveKitProvisioner._clear_conflicting_trunks(
        type("Client", (), {"sip": sip})(), "+19714361744", connection_id
    )
    assert sip.deleted == ["ST_stale"]


@pytest.mark.asyncio
async def test_trunk_owned_by_another_connection_raises():
    sip = FakeSipClient(
        [FakeInboundTrunk("ST_rT2teHJyoaoa", ["+19714361744"], "{}")]
    )
    with pytest.raises(RuntimeError, match="ST_rT2teHJyoaoa"):
        await LiveKitProvisioner._clear_conflicting_trunks(
            type("Client", (), {"sip": sip})(), "+19714361744", str(uuid.uuid4())
        )
    assert sip.deleted == []


@pytest.mark.asyncio
async def test_generic_sip_connection_provisions_and_returns_one_time_setup(
    client: AsyncClient,
    db_session: AsyncSession,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/phone-connections",
        headers=headers,
        json={
            "name": "Primary SIP",
            "provider": "generic_sip",
            "phone_number": "+96824000000",
            "agent_id": str(agent_a.id),
            "sip": {"transport": "tcp", "allowed_addresses": ["203.0.113.10/32"]},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"
    assert "password" not in created.text

    provisioned = await client.post(
        f"/api/v1/phone-connections/{created.json()['id']}/provision",
        headers=headers,
    )
    assert provisioned.status_code == 200, provisioned.text
    body = provisioned.json()
    assert body["connection"]["status"] == "testing"
    assert body["provider_setup"]["sip_uri"] == "sip:test.sip.livekit.cloud"
    assert body["provider_setup"]["username"].startswith("mw-")
    assert len(body["provider_setup"]["password"]) >= 24

    connection = await db_session.get(
        TelephonyConnection, uuid.UUID(created.json()["id"])
    )
    phone = await db_session.scalar(
        select(PhoneNumber).where(PhoneNumber.connection_id == connection.id)
    )
    assert "auth_password" not in (connection.configuration or {})
    assert connection.credentials_encrypted
    assert phone.is_enabled is True
    assert phone.connection_status == ConnectionStatus.PENDING


@pytest.mark.asyncio
async def test_first_inbound_call_activates_phone_connection(
    client: AsyncClient,
    db_session: AsyncSession,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/phone-connections",
        headers=headers,
        json={
            "name": "Verified SIP",
            "provider": "generic_sip",
            "phone_number": "+96824000001",
            "agent_id": str(agent_a.id),
        },
    )
    await client.post(
        f"/api/v1/phone-connections/{created.json()['id']}/provision",
        headers=headers,
    )

    inbound = await client.post(
        "/api/v1/internal/voice/calls",
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
        json={"phone_number": "+96824000001", "caller_number": "+96899000000"},
    )
    assert inbound.status_code == 201, inbound.text

    connection = await db_session.get(
        TelephonyConnection, uuid.UUID(created.json()["id"])
    )
    phone = await db_session.scalar(
        select(PhoneNumber).where(PhoneNumber.connection_id == connection.id)
    )
    assert connection.status == TelephonyConnectionStatus.ACTIVE
    assert connection.connected_at is not None
    assert phone.connection_status == ConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_duplicate_phone_connection_is_rejected(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    payload = {
        "name": "Duplicate",
        "provider": "generic_sip",
        "phone_number": "+96824000002",
        "agent_id": str(agent_a.id),
    }
    first = await client.post("/api/v1/phone-connections", headers=headers, json=payload)
    second = await client.post("/api/v1/phone-connections", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_other_company_cannot_read_phone_connection(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
    admin_b_token: str,
):
    created = await client.post(
        "/api/v1/phone-connections",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={
            "name": "Company A SIP",
            "provider": "generic_sip",
            "phone_number": "+96824000003",
            "agent_id": str(agent_a.id),
        },
    )
    response = await client.get(
        f"/api/v1/phone-connections/{created.json()['id']}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_twilio_connection_configures_elastic_sip_without_exposing_token(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    account_sid = "AC" + ("1" * 32)
    auth_token = "super-secret-twilio-token"
    phone_number_sid = "PN" + ("2" * 32)
    created = await client.post(
        "/api/v1/phone-connections",
        headers=headers,
        json={
            "name": "Twilio primary",
            "provider": "twilio",
            "phone_number": "+14155550100",
            "agent_id": str(agent_a.id),
            "twilio": {
                "account_sid": account_sid,
                "auth_token": auth_token,
                "phone_number_sid": phone_number_sid,
            },
        },
    )
    assert created.status_code == 201, created.text
    assert auth_token not in created.text

    provisioned = await client.post(
        f"/api/v1/phone-connections/{created.json()['id']}/provision",
        headers=headers,
    )
    assert provisioned.status_code == 200, provisioned.text
    assert provisioned.json()["provider_setup"]["configured_automatically"] is True
    assert provisioned.json()["connection"]["external_trunk_id"].startswith("TK")
    assert FakeTwilioClient.calls[0][0:2] == (account_sid, auth_token)
    assert FakeTwilioClient.calls[0][2]["phone_number_sid"] == phone_number_sid
