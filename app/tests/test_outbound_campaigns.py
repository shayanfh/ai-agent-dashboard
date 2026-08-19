import io
import uuid

import pytest

from app.modules.onboarding.models import (
    PhoneProvider,
    TelephonyConnection,
    TelephonyConnectionStatus,
    TelephonyConnectionType,
)


async def _connect_phone(db_session, company, phone):
    connection = TelephonyConnection(
        id=uuid.uuid4(),
        company_id=company.id,
        name="Outbound SIP",
        provider=PhoneProvider.GENERIC_SIP,
        connection_type=TelephonyConnectionType.SIP_TRUNK,
        status=TelephonyConnectionStatus.ACTIVE,
        asterisk_resource_id="pc-test",
    )
    db_session.add(connection)
    await db_session.flush()
    phone.connection_id = connection.id
    await db_session.flush()


@pytest.mark.asyncio
async def test_create_ai_campaign_is_tenant_scoped(
    client,
    db_session,
    company_a,
    phone_a,
    agent_a,
    admin_a_token,
    admin_b_token,
):
    await _connect_phone(db_session, company_a, phone_a)
    response = await client.post(
        "/api/v1/outbound-campaigns",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={
            "name": "Appointment confirmations",
            "campaign_type": "ai_conversation",
            "phone_number_id": str(phone_a.id),
            "agent_id": str(agent_a.id),
        },
    )
    assert response.status_code == 201, response.text
    campaign_id = response.json()["id"]
    assert response.json()["status"] == "draft"

    cross_tenant = await client.get(
        f"/api/v1/outbound-campaigns/{campaign_id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert cross_tenant.status_code == 404


@pytest.mark.asyncio
async def test_import_validates_deduplicates_and_applies_dnc(
    client,
    db_session,
    company_a,
    phone_a,
    admin_a_token,
):
    await _connect_phone(db_session, company_a, phone_a)
    auth = {"Authorization": f"Bearer {admin_a_token}"}
    dnc = await client.post(
        "/api/v1/outbound-campaigns/do-not-call",
        headers=auth,
        json={"phone_number": "+14155550102", "reason": "opted out"},
    )
    assert dnc.status_code == 201
    created = await client.post(
        "/api/v1/outbound-campaigns",
        headers=auth,
        json={
            "name": "Broadcast",
            "campaign_type": "voice_broadcast",
            "phone_number_id": str(phone_a.id),
            "message_text": "Your appointment is tomorrow.",
            "voice": "coral",
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    csv_content = (
        b"phone_number,first_name,external_id,custom_note\n"
        b"+14155550101,John,C-1,VIP\n"
        b"+14155550101,Duplicate,C-2,\n"
        b"+14155550102,Sarah,C-3,\n"
        b"invalid,Bad,C-4,\n"
    )
    imported = await client.post(
        f"/api/v1/outbound-campaigns/{campaign_id}/contacts/import",
        headers=auth,
        files={"file": ("contacts.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 2
    assert imported.json()["duplicates"] == 1
    assert imported.json()["rejected"] == 1

    recipients = await client.get(
        f"/api/v1/outbound-campaigns/{campaign_id}/recipients",
        headers=auth,
    )
    assert recipients.status_code == 200
    by_phone = {row["phone_number"]: row for row in recipients.json()["items"]}
    assert by_phone["+14155550101"]["custom_fields"] == {"custom_note": "VIP"}
    assert by_phone["+14155550102"]["status"] == "do_not_call"

    validation = await client.post(
        f"/api/v1/outbound-campaigns/{campaign_id}/validate",
        headers=auth,
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert "Generate and approve" in validation.json()["errors"][0]


@pytest.mark.asyncio
async def test_broadcast_requires_message(client, phone_a, admin_a_token):
    response = await client.post(
        "/api/v1/outbound-campaigns",
        headers={"Authorization": f"Bearer {admin_a_token}"},
        json={
            "name": "Invalid broadcast",
            "campaign_type": "voice_broadcast",
            "phone_number_id": str(phone_a.id),
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_and_get_tenant_scoped_broadcast_audio(
    client,
    db_session,
    company_a,
    phone_a,
    admin_a_token,
    admin_b_token,
    monkeypatch,
):
    await _connect_phone(db_session, company_a, phone_a)
    auth = {"Authorization": f"Bearer {admin_a_token}"}
    created = await client.post(
        "/api/v1/outbound-campaigns",
        headers=auth,
        json={
            "name": "Browser audio preview",
            "campaign_type": "voice_broadcast",
            "phone_number_id": str(phone_a.id),
            "message_text": "Old text",
        },
    )
    campaign_id = created.json()["id"]

    class FakeStorage:
        async def upload(self, source, *, key, content_type):
            return f"s3://test/{key}"

        async def presigned_download_url(self, *, key, expires_in):
            return f"https://storage.test/{key}?expires={expires_in}"

    async def generate_wav(_self, *, text, voice):
        assert text == "The current editor text"
        assert voice == "coral"
        return "a" * 64, b"RIFF0000WAVE"

    class FakeProvisioner:
        async def upload_outbound_media(self, media_id, wav):
            assert media_id == "a" * 64
            assert wav == b"RIFF0000WAVE"
            return {"media_id": media_id}

    monkeypatch.setattr(
        "app.modules.outbound_campaigns.service.get_object_storage",
        lambda: FakeStorage(),
    )
    monkeypatch.setattr(
        "app.modules.outbound_campaigns.service.CampaignTTS.generate_wav",
        generate_wav,
    )
    monkeypatch.setattr(
        "app.modules.outbound_campaigns.service.AsteriskProvisionerClient",
        FakeProvisioner,
    )

    generated = await client.post(
        f"/api/v1/outbound-campaigns/{campaign_id}/audio",
        headers=auth,
        json={"message_text": "The current editor text", "voice": "coral"},
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["media_id"] == "a" * 64

    playback = await client.get(
        f"/api/v1/outbound-campaigns/{campaign_id}/audio", headers=auth
    )
    assert playback.status_code == 200, playback.text
    assert playback.json()["url"].startswith("https://storage.test/outbound/")
    assert playback.json()["expires_in_seconds"] == 900

    cross_tenant = await client.get(
        f"/api/v1/outbound-campaigns/{campaign_id}/audio",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert cross_tenant.status_code == 404
