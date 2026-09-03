import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings, settings
from app.core.exceptions import IntegrationError, ValidationError
from app.modules.agents.schemas import ElevenLabsVoice, ElevenLabsVoiceListResponse

logger = logging.getLogger(__name__)


class ElevenLabsVoiceCatalog:
    """Merge My Voices with the full public library and import selections."""

    def __init__(
        self,
        app_settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = app_settings
        self._client = client
        self._voices: list[ElevenLabsVoice] | None = None
        self._library_index: dict[str, dict[str, Any]] = {}
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._voices = None
        self._library_index = {}
        self._expires_at = 0.0

    def _require_configuration(self) -> None:
        if not self.settings.ELEVENLABS_API_KEY:
            raise IntegrationError("ElevenLabs voice catalog is not configured")

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.ELEVENLABS_API_BASE_URL.rstrip("/"),
            timeout=self.settings.ELEVENLABS_REQUEST_TIMEOUT_SECONDS,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.settings.ELEVENLABS_API_KEY}

    async def list_voices(
        self, *, force_refresh: bool = False
    ) -> ElevenLabsVoiceListResponse:
        now = time.monotonic()
        if not force_refresh and self._voices is not None and now < self._expires_at:
            return ElevenLabsVoiceListResponse(
                voices=self._voices, total=len(self._voices), cached=True
            )

        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._voices is not None and now < self._expires_at:
                return ElevenLabsVoiceListResponse(
                    voices=self._voices, total=len(self._voices), cached=True
                )
            my_voices, library = await self._fetch_catalogs()
            self._library_index = {
                item["voice_id"]: item for item in library if item.get("voice_id")
            }
            merged = {
                voice.voice_id: voice
                for item in library
                if (voice := self._public_voice(item)).voice_id
            }
            # A My Voices entry wins over its public-library copy.
            merged.update({voice.voice_id: voice for voice in my_voices})
            voices = sorted(merged.values(), key=lambda voice: voice.name.casefold())
            self._voices = voices
            self._expires_at = now + self.settings.ELEVENLABS_VOICE_CACHE_SECONDS
            return ElevenLabsVoiceListResponse(
                voices=voices, total=len(voices), cached=False
            )

    async def _fetch_catalogs(
        self,
    ) -> tuple[list[ElevenLabsVoice], list[dict[str, Any]]]:
        self._require_configuration()
        owns_client = self._client is None
        client = self._client or self._new_client()
        try:
            return await asyncio.gather(
                self._fetch_my_voices(client), self._fetch_public_library(client)
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "ElevenLabs voice catalog request failed: %s", type(exc).__name__
            )
            raise IntegrationError("Could not load the ElevenLabs voice catalog") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _fetch_my_voices(
        self, client: httpx.AsyncClient
    ) -> list[ElevenLabsVoice]:
        voices: list[ElevenLabsVoice] = []
        next_page_token: str | None = None
        while True:
            params: dict[str, str | int | bool] = {
                "page_size": 100,
                "include_total_count": False,
                "sort": "name",
                "sort_direction": "asc",
            }
            if next_page_token:
                params["next_page_token"] = next_page_token
            response = await client.get(
                "/v2/voices", headers=self._headers, params=params
            )
            response.raise_for_status()
            body = response.json()
            voices.extend(
                ElevenLabsVoice.model_validate(
                    {**item, "in_my_voices": True, "public_owner_id": None}
                )
                for item in body.get("voices") or []
            )
            if not body.get("has_more"):
                break
            token = body.get("next_page_token")
            if not token or token == next_page_token:
                raise IntegrationError(
                    "ElevenLabs returned invalid My Voices pagination"
                )
            next_page_token = token
        return list({voice.voice_id: voice for voice in voices}.values())

    async def _fetch_public_library(
        self, client: httpx.AsyncClient
    ) -> list[dict[str, Any]]:
        voices: list[dict[str, Any]] = []
        page = 0
        previous_ids: tuple[str, ...] | None = None
        while True:
            response = await client.get(
                "/v1/shared-voices",
                headers=self._headers,
                params={"page": page, "page_size": 100},
            )
            response.raise_for_status()
            body = response.json()
            current = body.get("voices") or []
            current_ids = tuple(str(item.get("voice_id")) for item in current)
            if body.get("has_more") and (
                not current_ids or current_ids == previous_ids
            ):
                raise IntegrationError(
                    "ElevenLabs returned invalid Voice Library pagination"
                )
            voices.extend(current)
            if not body.get("has_more"):
                break
            previous_ids = current_ids
            page += 1
        return list(
            {item["voice_id"]: item for item in voices if item.get("voice_id")}.values()
        )

    @staticmethod
    def _public_voice(item: dict[str, Any]) -> ElevenLabsVoice:
        labels = {
            key: str(value)
            for key in (
                "gender",
                "age",
                "accent",
                "language",
                "use_case",
                "descriptive",
            )
            if (value := item.get(key)) is not None
        }
        return ElevenLabsVoice(
            voice_id=str(item.get("voice_id") or ""),
            name=str(item.get("name") or "Unnamed voice"),
            category=item.get("category"),
            description=item.get("description"),
            preview_url=item.get("preview_url"),
            labels=labels,
            public_owner_id=item.get("public_owner_id"),
            in_my_voices=False,
        )

    async def ensure_voice_in_my_voices(self, voice_id: str) -> bool:
        """Import a selected public voice if it is not already in My Voices."""
        self._require_configuration()
        async with self._lock:
            owns_client = self._client is None
            client = self._client or self._new_client()
            try:
                my_voices = await self._fetch_my_voices(client)
                if any(voice.voice_id == voice_id for voice in my_voices):
                    return False

                item = self._library_index.get(voice_id)
                if item is None:
                    library = await self._fetch_public_library(client)
                    self._library_index = {
                        candidate["voice_id"]: candidate
                        for candidate in library
                        if candidate.get("voice_id")
                    }
                    item = self._library_index.get(voice_id)
                if item is None or not item.get("public_owner_id"):
                    raise ValidationError("Selected ElevenLabs voice was not found")

                owner_path = quote(str(item["public_owner_id"]), safe="")
                voice_path = quote(voice_id, safe="")
                response = await client.post(
                    f"/v1/voices/add/{owner_path}/{voice_path}",
                    headers=self._headers,
                    json={"new_name": str(item.get("name") or voice_id)},
                )
                response.raise_for_status()
                self.invalidate()
                return True
            except ValidationError:
                raise
            except httpx.HTTPError as exc:
                logger.warning(
                    "ElevenLabs automatic voice import failed: %s",
                    type(exc).__name__,
                )
                raise IntegrationError(
                    "Could not add the selected voice to My Voices"
                ) from exc
            finally:
                if owns_client:
                    await client.aclose()


voice_catalog = ElevenLabsVoiceCatalog(settings)
