import uuid
from typing import ClassVar

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.calls.models import Call
from app.modules.extensions.models import Extension
from app.modules.phone_connections.providers import AsteriskResource


class FakeExtensionProvisioner:
    provisioned: ClassVar[list[tuple[str, dict]]] = []
    deleted: ClassVar[list[str]] = []

    async def provision_extension(
        self, extension_id: str, payload: dict
    ) -> AsteriskResource:
        self.provisioned.append((extension_id, payload))
        return AsteriskResource(f"ext-{extension_id}", "configured", {})

    async def delete_extension(self, resource_id: str | None) -> None:
        if resource_id:
            self.deleted.append(resource_id)


@pytest.fixture(autouse=True)
def fake_extension_provisioner(monkeypatch):
    FakeExtensionProvisioner.provisioned.clear()
    FakeExtensionProvisioner.deleted.clear()
    monkeypatch.setattr(
        settings, "ASTERISK_PUBLIC_SIP_URI", "sip:pbx.test:5061;transport=tls"
    )
    monkeypatch.setattr(
        "app.modules.extensions.service.AsteriskProvisionerClient",
        FakeExtensionProvisioner,
    )


@pytest.mark.asyncio
async def test_extension_credentials_lifecycle_and_transfer_target(
    client: AsyncClient,
    db_session: AsyncSession,
    call_a: Call,
    admin_a_token: str,
    admin_b_token: str,
):
    headers_a = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/extensions",
        headers=headers_a,
        json={
            "extension": "100",
            "display_name": "Sales",
            "employee_name": "Ali",
            "transport": "tls",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    extension_id = uuid.UUID(body["extension"]["id"])
    password = body["credentials"]["password"]
    assert body["credentials"] == {
        "server": "pbx.test",
        "port": 5061,
        "transport": "tls",
        "username": body["extension"]["sip_username"],
        "password": password,
        "extension": "100",
    }
    assert password not in str(FakeExtensionProvisioner.provisioned[0][0])
    assert FakeExtensionProvisioner.provisioned[0][1]["sip_password"] == password

    stored = await db_session.get(Extension, extension_id)
    assert stored is not None
    assert stored.sip_password_encrypted != password

    fetched = await client.get(f"/api/v1/extensions/{extension_id}", headers=headers_a)
    assert fetched.status_code == 200
    assert password not in fetched.text
    assert "credentials" not in fetched.json()

    denied = await client.get(
        f"/api/v1/extensions/{extension_id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert denied.status_code == 404

    created_b = await client.post(
        "/api/v1/extensions",
        headers={"Authorization": f"Bearer {admin_b_token}"},
        json={"extension": "100", "display_name": "Company B Sales"},
    )
    assert created_b.status_code == 201, created_b.text
    assert (
        created_b.json()["extension"]["company_id"] != body["extension"]["company_id"]
    )

    target = await client.post(
        f"/api/v1/internal/voice/calls/{call_a.id}/transfer-target",
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
        json={"extension": "100"},
    )
    assert target.status_code == 200, target.text
    assert target.json()["extension_id"] == str(extension_id)
    assert target.json()["sip_uri"].startswith("sip:x")
    assert target.json()["sip_uri"].endswith("@pbx.test:5061;transport=tls")

    rotated = await client.post(
        f"/api/v1/extensions/{extension_id}/rotate-password", headers=headers_a
    )
    assert rotated.status_code == 200
    assert rotated.json()["credentials"]["password"] != password

    disabled = await client.post(
        f"/api/v1/extensions/{extension_id}/disable", headers=headers_a
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    unavailable = await client.post(
        f"/api/v1/internal/voice/calls/{call_a.id}/transfer-target",
        headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
        json={"extension": "100"},
    )
    assert unavailable.status_code == 404

    deleted = await client.delete(
        f"/api/v1/extensions/{extension_id}", headers=headers_a
    )
    assert deleted.status_code == 204
    assert FakeExtensionProvisioner.deleted == [f"ext-{extension_id}"]
    assert await db_session.get(Extension, extension_id) is None


def test_phone_number_contract_no_longer_contains_extension():
    from app.main import app

    schema = app.openapi()
    create_schema = schema["components"]["schemas"]["PhoneNumberCreate"]
    response_schema = schema["components"]["schemas"]["PhoneNumberResponse"]
    assert "extension" not in create_schema["properties"]
    assert "extension" not in response_schema["properties"]
