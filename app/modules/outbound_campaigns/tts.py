import hashlib
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)


class CampaignTTS:
    async def generate_wav(self, *, text: str, voice: str) -> tuple[str, bytes]:
        if not settings.OPENAI_API_KEY:
            raise IntegrationError("Outbound TTS is not configured")
        media_id = hashlib.sha256(
            f"{settings.TTS_PREVIEW_MODEL}\0{voice}\0{text}".encode()
        ).hexdigest()
        try:
            async with httpx.AsyncClient(
                base_url="https://api.openai.com",
                timeout=settings.TTS_PREVIEW_TIMEOUT_SECONDS,
            ) as client:
                response = await client.post(
                    "/v1/audio/speech",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": settings.TTS_PREVIEW_MODEL,
                        "input": text,
                        "voice": voice,
                        "response_format": "wav",
                    },
                )
                response.raise_for_status()
                return media_id, response.content
        except httpx.HTTPError as exc:
            logger.warning("Outbound TTS generation failed", exc_info=True)
            raise IntegrationError("Outbound TTS generation failed") from exc
