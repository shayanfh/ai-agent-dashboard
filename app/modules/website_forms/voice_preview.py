import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)

VoiceName = Literal[
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
]

GREETING_TEMPLATE = (
    "Thanks for calling {}. You're through to the AI agent — "
    "how can I help you today?"
)


class VoicePreviewRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=100)
    voice: VoiceName = "coral"

    @field_validator("company_name")
    @classmethod
    def normalize_company_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Company name cannot be empty")
        return normalized


class VoicePreviewService:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def generate(self, data: VoicePreviewRequest) -> bytes:
        if not settings.OPENAI_API_KEY:
            raise IntegrationError("Voice preview service is not configured")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url="https://api.openai.com",
            timeout=settings.TTS_PREVIEW_TIMEOUT_SECONDS,
        )
        try:
            response = await client.post(
                "/v1/audio/speech",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.TTS_PREVIEW_MODEL,
                    "input": GREETING_TEMPLATE.format(data.company_name),
                    "voice": data.voice,
                    "response_format": "mp3",
                },
            )
            if not response.is_success:
                logger.warning(
                    "OpenAI voice preview request failed with status %s",
                    response.status_code,
                )
                raise IntegrationError("Voice preview generation failed")
            return response.content
        except httpx.HTTPError as exc:
            raise IntegrationError("Voice preview service is unavailable") from exc
        finally:
            if owns_client:
                await client.aclose()
