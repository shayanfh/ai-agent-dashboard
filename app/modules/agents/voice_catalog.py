import asyncio
import logging
import math
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings, settings
from app.core.exceptions import IntegrationError, ValidationError
from app.modules.agents.schemas import (
    ElevenLabsVoice,
    ElevenLabsVoiceListResponse,
)

logger = logging.getLogger(__name__)


class ElevenLabsVoiceCatalog:
    """Page through ElevenLabs Voice Library and import selected voices."""

    def __init__(
        self,
        app_settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = app_settings
        self._client = client
        self._page_cache: dict[
            tuple[int, int, str, str, str],
            tuple[float, ElevenLabsVoiceListResponse],
        ] = {}
        self._my_voice_ids: set[str] | None = None
        self._my_voices_expires_at = 0.0
        self._library_index: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        # Keep public owner metadata so the next selection does not rediscover it.
        self._page_cache = {}
        self._my_voice_ids = None
        self._my_voices_expires_at = 0.0

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
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        language: str | None = None,
        accent: str | None = None,
        force_refresh: bool = False,
    ) -> ElevenLabsVoiceListResponse:
        """Return one provider-side page instead of downloading the full library."""
        self._require_configuration()
        normalized_search = (search or "").strip()
        normalized_language = (language or "").strip()
        normalized_accent = (accent or "").strip()
        cache_key = (
            page,
            page_size,
            normalized_search.casefold(),
            normalized_language.casefold(),
            normalized_accent.casefold(),
        )
        now = time.monotonic()
        cached = self._page_cache.get(cache_key)
        if not force_refresh and cached is not None and now < cached[0]:
            return cached[1].model_copy(update={"cached": True})

        async with self._lock:
            now = time.monotonic()
            cached = self._page_cache.get(cache_key)
            if not force_refresh and cached is not None and now < cached[0]:
                return cached[1].model_copy(update={"cached": True})

            owns_client = self._client is None
            client = self._client or self._new_client()
            try:
                library_task = self._fetch_public_library_page(
                    client,
                    page=page,
                    page_size=page_size,
                    search=normalized_search or None,
                    language=normalized_language or None,
                    accent=normalized_accent or None,
                )
                my_ids_task = self._get_my_voice_ids(
                    client, force_refresh=force_refresh
                )
                (items, total, has_more), my_voice_ids = await asyncio.gather(
                    library_task, my_ids_task
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "ElevenLabs voice catalog request failed: %s", type(exc).__name__
                )
                raise IntegrationError(
                    "Could not load the ElevenLabs voice catalog"
                ) from exc
            finally:
                if owns_client:
                    await client.aclose()

            for item in items:
                voice_id = item.get("voice_id")
                if voice_id:
                    self._library_index[str(voice_id)] = item

            if normalized_search:
                ranked_items = [
                    (self._search_rank(item, normalized_search), item)
                    for item in items
                ]
                # ElevenLabs search is fuzzy and may return `woman` for `oman`.
                # Keep only token-prefix matches from actual voice metadata.
                items = [
                    item
                    for rank, item in sorted(ranked_items, key=lambda entry: entry[0])
                    if rank < 3
                ]
                if page == 1 and not has_more:
                    total = len(items)

            voices: list[ElevenLabsVoice] = []
            for item in items:
                voice = self._public_voice(item)
                voice.in_my_voices = voice.voice_id in my_voice_ids
                voices.append(voice)

            result = ElevenLabsVoiceListResponse(
                voices=voices,
                total=total,
                page=page,
                page_size=page_size,
                pages=math.ceil(total / page_size) if total else 0,
                cached=False,
            )
            self._page_cache[cache_key] = (
                now + self.settings.ELEVENLABS_VOICE_CACHE_SECONDS,
                result,
            )
            return result

    async def _get_my_voice_ids(
        self, client: httpx.AsyncClient, *, force_refresh: bool = False
    ) -> set[str]:
        now = time.monotonic()
        if (
            not force_refresh
            and self._my_voice_ids is not None
            and now < self._my_voices_expires_at
        ):
            return self._my_voice_ids
        voices = await self._fetch_my_voices(client)
        self._my_voice_ids = {voice.voice_id for voice in voices}
        self._my_voices_expires_at = (
            now + self.settings.ELEVENLABS_VOICE_CACHE_SECONDS
        )
        return self._my_voice_ids

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

    async def _fetch_public_library_page(
        self,
        client: httpx.AsyncClient,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        language: str | None = None,
        accent: str | None = None,
    ) -> tuple[list[dict[str, Any]], int, bool]:
        params: dict[str, str | int] = {
            "page": page - 1,
            "page_size": page_size,
            "sort": "trending",
        }
        if search:
            params["search"] = search
        if language:
            params["language"] = language
        if accent:
            params["accent"] = accent
        response = await client.get(
            "/v1/shared-voices", headers=self._headers, params=params
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("voices") or []
        return (
            items,
            int(body.get("total_count") or len(items)),
            bool(body.get("has_more")),
        )

    @staticmethod
    def _search_rank(item: dict[str, Any], search: str) -> int:
        """Put literal metadata matches before ElevenLabs' fuzzy matches.

        `verified_languages` participates only in ranking and is never included
        in the public response schema.
        """
        terms = re.findall(r"[^\W_]+", search.casefold(), flags=re.UNICODE)
        if not terms:
            return 3
        values = [
            item.get("voice_id"),
            item.get("name"),
            item.get("description"),
            item.get("category"),
            item.get("language"),
            item.get("locale"),
            item.get("accent"),
            item.get("gender"),
            item.get("age"),
            item.get("use_case"),
            item.get("descriptive"),
        ]
        for verified in item.get("verified_languages") or []:
            if isinstance(verified, dict):
                values.extend(
                    [
                        verified.get("language"),
                        verified.get("locale"),
                        verified.get("accent"),
                    ]
                )
        normalized = [str(value).casefold() for value in values if value is not None]
        tokens = [
            token
            for value in normalized
            for token in re.findall(r"[^\W_]+", value, flags=re.UNICODE)
        ]
        if all(term in normalized or term in tokens for term in terms):
            return 0
        if all(any(token.startswith(term) for token in tokens) for term in terms):
            return 1
        return 3

    async def _fetch_public_library(
        self, client: httpx.AsyncClient
    ) -> list[dict[str, Any]]:
        """Fallback lookup used only when a voice was not listed by this worker."""
        voices: list[dict[str, Any]] = []
        page = 1
        while True:
            response = await client.get(
                "/v1/shared-voices",
                headers=self._headers,
                params={"page": page - 1, "page_size": 100},
            )
            response.raise_for_status()
            body = response.json()
            current = body.get("voices") or []
            voices.extend(current)
            if not body.get("has_more"):
                break
            if not current:
                raise IntegrationError(
                    "ElevenLabs returned invalid Voice Library pagination"
                )
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
                my_voice_ids = await self._get_my_voice_ids(
                    client, force_refresh=True
                )
                if voice_id in my_voice_ids:
                    return False

                item = self._library_index.get(voice_id)
                if item is None:
                    library = await self._fetch_public_library(client)
                    self._library_index.update(
                        {
                            str(candidate["voice_id"]): candidate
                            for candidate in library
                            if candidate.get("voice_id")
                        }
                    )
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
