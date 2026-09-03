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
    AsteriskResource,
    LiveKitProvisioner,
    LiveKitResources,
    TwilioTrunkResource,
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

    async def provision(self, **kwargs) -> TwilioTrunkResource:
        self.calls.append((self.account_sid, self.auth_token, kwargs))
        return TwilioTrunkResource(
            trunk_sid="TK0123456789abcdef0123456789abcdef",
            domain="mw-test.pstn.twilio.com",
            credential_list_sid="CL0123456789abcdef0123456789abcdef",
            sip_username="mw-test",
            sip_password="generated-test-password-1234567890",
        )

    async def delete(self, trunk_sid: str, credential_list_sid: str | None = None) -> None:
        return None


class FakeAsteriskProvisioner:
    calls: ClassVar[list[tuple[str, dict]]] = []
    deleted: ClassVar[list[str]] = []

    async def provision(self, connection_id: str, payload: dict) -> AsteriskResource:
        self.calls.append((connection_id, payload))
        mode = payload["mode"]
        return AsteriskResource(
            resource_id=f"pc-{connection_id}",
            state="registering" if mode == "registration" else "configured",
            provider_setup={
                "configured_asterisk": True,
                "provider_action_required": mode == "ip_trunk",
                **(
                    {"destination_sip_uri": f"sip:{payload['phone_number']}@sip.test"}
                    if mode == "ip_trunk"
                    else {}
                ),
            },
        )

    async def status(self, resource_id: str) -> AsteriskResource:
        return AsteriskResource(resource_id, "configured", {})

    async def delete(self, resource_id: str | None) -> None:
        if resource_id:
            self.deleted.append(resource_id)


@pytest.fixture(autouse=True)
def fake_livekit(monkeypatch):
    FakeLiveKitProvisioner.deleted.clear()
    monkeypatch.setattr(settings, "LIVEKIT_SIP_ENDPOINT", "test.sip.livekit.cloud")
    monkeypatch.setattr(
        settings, "ASTERISK_PUBLIC_SIP_URI", "sip:sip.test:5061;transport=tls"
    )
    FakeAsteriskProvisioner.calls.clear()
    FakeAsteriskProvisioner.deleted.clear()
    monkeypatch.setattr(
        "app.modules.phone_connections.service.AsteriskProvisionerClient",
        FakeAsteriskProvisioner,
    )
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
        "/api/v1/phone-numbers",
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
        f"/api/v1/phone-numbers/{created.json()['id']}/provision",
        headers=headers,
    )
    assert provisioned.status_code == 200, provisioned.text
    body = provisioned.json()
    assert body["phone_number"]["status"] == "awaiting_provider_setup"
    assert body["provider_setup"]["gateway"] == "asterisk"
    assert body["provider_setup"]["provider_action_required"] is True
    assert body["provider_setup"]["destination_sip_uri"].startswith("sip:+96824000000@")

    connection = await db_session.get(
        TelephonyConnection, uuid.UUID(created.json()["connection_id"])
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
        "/api/v1/phone-numbers",
        headers=headers,
        json={
            "name": "Verified SIP",
            "provider": "generic_sip",
            "phone_number": "+96824000001",
            "agent_id": str(agent_a.id),
            "sip": {
                "mode": "ip_trunk",
                "allowed_addresses": ["203.0.113.10/32"],
            },
        },
    )
    await client.post(
        f"/api/v1/phone-numbers/{created.json()['id']}/provision",
        headers=headers,
    )

    inbound = await client.post(
        "/api/v1/internal/voice/calls",
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
        json={"phone_number": "+96824000001", "caller_number": "+96899000000"},
    )
    assert inbound.status_code == 201, inbound.text

    connection = await db_session.get(
        TelephonyConnection, uuid.UUID(created.json()["connection_id"])
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
        "sip": {
            "mode": "ip_trunk",
            "allowed_addresses": ["203.0.113.10/32"],
        },
    }
    first = await client.post("/api/v1/phone-numbers", headers=headers, json=payload)
    second = await client.post("/api/v1/phone-numbers", headers=headers, json=payload)
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
        "/api/v1/phone-numbers",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={
            "name": "Company A SIP",
            "provider": "generic_sip",
            "phone_number": "+96824000003",
            "agent_id": str(agent_a.id),
            "sip": {
                "mode": "ip_trunk",
                "allowed_addresses": ["203.0.113.10/32"],
            },
        },
    )
    response = await client.get(
        f"/api/v1/phone-numbers/{created.json()['id']}",
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
        "/api/v1/phone-numbers",
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
        f"/api/v1/phone-numbers/{created.json()['id']}/provision",
        headers=headers,
    )
    assert provisioned.status_code == 200, provisioned.text
    assert provisioned.json()["provider_setup"]["configured_automatically"] is True
    assert provisioned.json()["phone_number"]["external_trunk_id"].startswith("TK")
    assert FakeTwilioClient.calls[0][0:2] == (account_sid, auth_token)
    assert FakeTwilioClient.calls[0][2]["phone_number_sid"] == phone_number_sid
    assert FakeTwilioClient.calls[0][2]["target_sip_uri"] == (
        "sip:sip.test:5061;transport=tls"
    )
    assert FakeAsteriskProvisioner.calls[0][1]["mode"] == "twilio"


@pytest.mark.asyncio
async def test_generic_sip_registration_is_configured_on_asterisk(
    client: AsyncClient,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/phone-numbers",
        headers=headers,
        json={
            "name": "Registered provider",
            "provider": "generic_sip",
            "phone_number": "+96824000005",
            "agent_id": str(agent_a.id),
            "sip": {
                "mode": "registration",
                "server_uri": "sip.provider.test",
                "auth_username": "customer100",
                "auth_password": "provider-secret-123",
                "transport": "tls",
            },
        },
    )
    provisioned = await client.post(
        f"/api/v1/phone-numbers/{created.json()['id']}/provision",
        headers=headers,
    )

    assert provisioned.status_code == 200, provisioned.text
    assert provisioned.json()["phone_number"]["status"] == "registering"
    payload = FakeAsteriskProvisioner.calls[0][1]
    assert payload["mode"] == "registration"
    assert payload["server_uri"] == "sip.provider.test"
    assert payload["auth_password"] == "provider-secret-123"
    assert "provider-secret-123" not in provisioned.text


@pytest.mark.asyncio
async def test_delete_disconnects_before_removing_connection_and_phone_mapping(
    client: AsyncClient,
    db_session: AsyncSession,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/phone-numbers",
        headers=headers,
        json={
            "name": "Disposable SIP",
            "provider": "generic_sip",
            "phone_number": "+96824000004",
            "agent_id": str(agent_a.id),
            "sip": {
                "mode": "ip_trunk",
                "allowed_addresses": ["203.0.113.10/32"],
            },
        },
    )
    phone_id = uuid.UUID(created.json()["id"])
    connection_id = uuid.UUID(created.json()["connection_id"])
    provisioned = await client.post(
        f"/api/v1/phone-numbers/{phone_id}/provision",
        headers=headers,
    )
    assert provisioned.status_code == 200, provisioned.text
    deleted = await client.delete(
        f"/api/v1/phone-numbers/{phone_id}", headers=headers
    )

    assert deleted.status_code == 204
    assert FakeLiveKitProvisioner.deleted == []
    assert FakeAsteriskProvisioner.deleted == [f"pc-{connection_id}"]
    assert await db_session.get(TelephonyConnection, connection_id) is None
    assert await db_session.get(PhoneNumber, phone_id) is None
    missing = await client.get(
        f"/api/v1/phone-numbers/{phone_id}", headers=headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_phone_numbers_is_the_unified_public_telephony_api(
    client: AsyncClient,
    db_session: AsyncSession,
    agent_a: Agent,
    admin_a_token: str,
):
    headers = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/phone-numbers",
        headers=headers,
        json={
            "name": "Dashboard number",
            "provider": "generic_sip",
            "phone_number": "+96824000006",
            "agent_id": str(agent_a.id),
            "sip": {
                "mode": "ip_trunk",
                "allowed_addresses": ["203.0.113.10/32"],
            },
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    phone_id = uuid.UUID(body["id"])
    connection_id = uuid.UUID(body["connection_id"])
    assert phone_id != connection_id
    assert body["name"] == "Dashboard number"
    assert body["status"] == "pending"
    assert body["provider"] == "generic_sip"

    listed = await client.get("/api/v1/phone-numbers", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == str(phone_id) for item in listed.json()["items"])

    provisioned = await client.post(
        f"/api/v1/phone-numbers/{phone_id}/provision", headers=headers
    )
    assert provisioned.status_code == 200, provisioned.text
    assert provisioned.json()["phone_number"]["id"] == str(phone_id)
    assert (
        provisioned.json()["phone_number"]["status"]
        == "awaiting_provider_setup"
    )

    tested = await client.post(
        f"/api/v1/phone-numbers/{phone_id}/test", headers=headers
    )
    assert tested.status_code == 200
    assert tested.json()["success"] is True

    disconnected = await client.post(
        f"/api/v1/phone-numbers/{phone_id}/disconnect", headers=headers
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "disconnected"

    deleted = await client.delete(
        f"/api/v1/phone-numbers/{phone_id}", headers=headers
    )
    assert deleted.status_code == 204
    assert await db_session.get(PhoneNumber, phone_id) is None
    assert await db_session.get(TelephonyConnection, connection_id) is None


@pytest.mark.asyncio
async def test_phone_connections_routes_are_removed(
    client: AsyncClient, admin_a_token: str
):
    from app.main import app

    schema = app.openapi()
    assert not any(path.startswith("/api/v1/phone-connections") for path in schema["paths"])
    response = await client.get(
        "/api/v1/phone-connections",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 404
