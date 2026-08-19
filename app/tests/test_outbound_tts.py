import io
import math
import struct
import wave

from app.modules.outbound_campaigns.tts import normalize_wav_for_asterisk


def _wav(*, sample_rate: int, channels: int) -> bytes:
    frames = bytearray()
    for index in range(sample_rate // 10):
        sample = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", sample) * channels)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))
    return output.getvalue()


def test_normalizes_tts_wav_for_asterisk() -> None:
    normalized = normalize_wav_for_asterisk(_wav(sample_rate=24000, channels=2))

    with wave.open(io.BytesIO(normalized), "rb") as wav_file:
        assert wav_file.getcomptype() == "NONE"
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 8000
        assert 790 <= wav_file.getnframes() <= 810
