from urllib.parse import urlparse

import pytest

from app.core.config import Settings
from app.core.storage import ObjectStorage


@pytest.mark.asyncio
async def test_presigned_recording_url_uses_public_nginx_origin_and_bucket_path() -> None:
    storage = ObjectStorage(
        Settings(
            STORAGE_ENDPOINT="http://minio:9000",
            STORAGE_PUBLIC_ENDPOINT="https://api.example.com",
            STORAGE_ACCESS_KEY="test-access-key",
            STORAGE_SECRET_KEY="test-secret-key",
            STORAGE_BUCKET="recordings",
        )
    )

    url = await storage.presigned_download_url(
        key="recordings/asterisk/company/call.wav",
        expires_in=900,
    )
    parsed = urlparse(url)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.example.com"
    assert parsed.path == "/recordings/recordings/asterisk/company/call.wav"
    assert "X-Amz-Signature=" in parsed.query
