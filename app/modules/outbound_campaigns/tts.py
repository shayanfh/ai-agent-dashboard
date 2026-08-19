import audioop
import hashlib
import io
import logging
import wave

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)
ASTERISK_SAMPLE_RATE = 8000
ASTERISK_AUDIO_VERSION = "pcm16-mono-8khz-v1"


def normalize_wav_for_asterisk(content: bytes) -> bytes:
    """Convert an uncompressed WAV to Asterisk-safe PCM16 mono at 8 kHz."""
    try:
        with wave.open(io.BytesIO(content), "rb") as source:
            if source.getcomptype() != "NONE":
                raise IntegrationError("Outbound TTS returned compressed WAV audio")
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            frames = source.readframes(source.getnframes())
        if channels not in (1, 2) or sample_width not in (1, 2, 3, 4):
            raise IntegrationError("Outbound TTS returned an unsupported WAV format")
        if channels == 2:
            frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        if sample_width != 2:
            frames = audioop.lin2lin(frames, sample_width, 2)
        if sample_rate != ASTERISK_SAMPLE_RATE:
            frames, _ = audioop.ratecv(
                frames,
                2,
                1,
                sample_rate,
                ASTERISK_SAMPLE_RATE,
                None,
            )
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(ASTERISK_SAMPLE_RATE)
            target.writeframes(frames)
        return output.getvalue()
    except (EOFError, ValueError, wave.Error, audioop.error) as exc:
        raise IntegrationError("Outbound TTS returned invalid WAV audio") from exc


class CampaignTTS:
    async def generate_wav(self, *, text: str, voice: str) -> tuple[str, bytes]:
        if not settings.OPENAI_API_KEY:
            raise IntegrationError("Outbound TTS is not configured")
        media_id = hashlib.sha256(
            f"{ASTERISK_AUDIO_VERSION}\0{settings.TTS_PREVIEW_MODEL}\0{voice}\0{text}".encode()
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
                return media_id, normalize_wav_for_asterisk(response.content)
        except httpx.HTTPError as exc:
            logger.warning("Outbound TTS generation failed", exc_info=True)
            raise IntegrationError("Outbound TTS generation failed") from exc
