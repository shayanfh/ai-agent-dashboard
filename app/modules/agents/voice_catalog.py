import asyncio
import logging
import time

import httpx

from app.core.config import Settings, settings
from app.core.exceptions import IntegrationError
from app.modules.agents.schemas import ElevenLabsVoice, ElevenLabsVoiceListResponse

logger = logging.getLogger(__name__)


class ElevenLabsVoiceCatalog:
    """Fetch and briefly cache every voice available to the platform account."""

    def __init__(
        self,
        app_settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = app_settings
        self._client = client
        self._voices: list[ElevenLabsVoice] | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def list_voices(self, *, force_refresh: bool = False) -> ElevenLabsVoiceListResponse:
        now = time.monotonic()
        if not force_refresh and self._voices is not None and now < self._expires_at:
            return ElevenLabsVoiceListResponse(
                voices=self._voices,
                total=len(self._voices),
                cached=True,
            )

        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._voices is not None and now < self._expires_at:
                return ElevenLabsVoiceListResponse(
                    voices=self._voices,
                    total=len(self._voices),
                    cached=True,
                )
            voices = await self._fetch_all()
            self._voices = voices
            self._expires_at = now + self.settings.ELEVENLABS_VOICE_CACHE_SECONDS
            return ElevenLabsVoiceListResponse(
                voices=voices,
                total=len(voices),
                cached=False,
            )

    async def _fetch_all(self) -> list[ElevenLabsVoice]:
        if not self.settings.ELEVENLABS_API_KEY:
            raise IntegrationError("ElevenLabs voice catalog is not configured")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.ELEVENLABS_API_BASE_URL.rstrip("/"),
            timeout=self.settings.ELEVENLABS_REQUEST_TIMEOUT_SECONDS,
        )
        voices: list[ElevenLabsVoice] = []
        next_page_token: str | None = None
        try:
            for _ in range(100):
                params: dict[str, str | int | bool] = {
                    "page_size": 100,
                    "include_total_count": False,
                    "sort": "name",
                    "sort_direction": "asc",
                }
                if next_page_token:
                    params["next_page_token"] = next_page_token
                response = await client.get(
                    "/v2/voices",
                    headers={"xi-api-key": self.settings.ELEVENLABS_API_KEY},
                    params=params,
                )
                response.raise_for_status()
                body = response.json()
                voices.extend(
                    ElevenLabsVoice.model_validate(item)
                    for item in body.get("voices") or []
                )
                if not body.get("has_more"):
                    break
                next_page_token = body.get("next_page_token")
                if not next_page_token:
                    raise IntegrationError("ElevenLabs returned invalid voice pagination")
            else:
                raise IntegrationError("ElevenLabs voice pagination exceeded the safety limit")
        except httpx.HTTPError as exc:
            logger.warning("ElevenLabs voice catalog request failed: %s", type(exc).__name__)
            raise IntegrationError("Could not load the ElevenLabs voice catalog") from exc
        finally:
            if owns_client:
                await client.aclose()

        # Defensive de-duplication in case voices move between pages during pagination.
        unique = {voice.voice_id: voice for voice in voices}
        return sorted(unique.values(), key=lambda voice: voice.name.casefold())


voice_catalog = ElevenLabsVoiceCatalog(settings)
