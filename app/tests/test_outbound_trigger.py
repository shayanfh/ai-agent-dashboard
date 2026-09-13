import uuid
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.workers.outbound_tasks import _trigger_standalone_tts_call


class _FakeSession:
    def __init__(self, connection_id):
        self.connection_id = connection_id

    async def scalar(self, _query):
        return SimpleNamespace(connection_id=self.connection_id)


class _FakeSessionContext:
    def __init__(self, connection_id):
        self.session = _FakeSession(connection_id)

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_standalone_tts_call_only_reads_source_and_calls_provisioner(monkeypatch):
    connection_id = uuid.uuid4()
    captured = {}
    monkeypatch.setattr(settings, "TTS_OUTBOUND_SOURCE_NUMBER", "+96822388881")
    monkeypatch.setattr(settings, "TTS_OUTBOUND_DESTINATION_NUMBER", "+96897737034")
    monkeypatch.setattr(settings, "TTS_OUTBOUND_VOICE", "coral")
    monkeypatch.setattr(settings, "ASTERISK_PROVISIONER_URL", "https://asterisk.test")
    monkeypatch.setattr(settings, "ASTERISK_PROVISIONER_API_KEY", "test-key")
    monkeypatch.setattr(
        settings,
        "ASTERISK_PUBLIC_SIP_URI",
        "sip:asterisk.test:5060;transport=udp",
    )
    monkeypatch.setattr(
        "app.workers.outbound_tasks.AsyncSessionLocal",
        lambda: _FakeSessionContext(connection_id),
    )

    async def generate_wav(_self, *, text, voice):
        captured["tts"] = (text, voice)
        return "a" * 64, b"wav"

    async def upload_media(_self, media_id, wav):
        captured["upload"] = (media_id, wav)
        return {}

    async def originate(_self, payload):
        captured["payload"] = payload
        return {"provider_call_id": "test-call"}

    monkeypatch.setattr(
        "app.workers.outbound_tasks.CampaignTTS.generate_wav", generate_wav
    )
    monkeypatch.setattr(
        "app.workers.outbound_tasks.AsteriskProvisionerClient.upload_outbound_media",
        upload_media,
    )
    monkeypatch.setattr(
        "app.workers.outbound_tasks.AsteriskProvisionerClient.originate_outbound",
        originate,
    )

    await _trigger_standalone_tts_call("Standalone message")

    assert captured["tts"] == ("Standalone message", "coral")
    assert captured["upload"] == ("a" * 64, b"wav")
    assert captured["payload"]["connection_id"] == str(connection_id)
    assert captured["payload"]["caller_id"] == "+96822388881"
    assert captured["payload"]["destination_number"] == "+96897737034"
    assert captured["payload"]["report_events"] is False

