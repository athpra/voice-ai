import asyncio
import io
import wave
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.config import settings
from app.stt.base import STTProvider, Transcript

# Whisper/Riva served through Cloudera AI Inference Service's OpenAI-compatible
# API only exposes the standard batch /v1/audio/transcriptions contract (whole
# clip in, transcript out) -- there is no websocket/streaming shape in that
# API regardless of how the underlying serving performs. So this provider
# buffers each utterance locally using simple energy-based silence detection,
# then sends one HTTP request per turn instead of a persistent connection.
#
# Not yet exercised against a live endpoint -- confirm CAII_STT_MODEL_NAME and
# the response shape against your actual deployment before relying on it.

SILENCE_RMS_THRESHOLD = 500  # int16 scale (0-32767); tune against your line/mic noise floor
SILENCE_DURATION_MS = 700  # trailing silence required to treat an utterance as complete
MIN_SPEECH_MS = 300  # ignore blips shorter than this so silence alone doesn't trigger a flush
MAX_UTTERANCE_MS = 15000  # safety cap so a stuck-open mic can't buffer forever
CHUNK_MS = 20  # Twilio sends mulaw audio in ~20ms frames
SAMPLE_RATE = 8000

_MULAW_DECODE_EXP_LUT = [0, 132, 396, 924, 1980, 4092, 8316, 16764]


def _mulaw_byte_to_linear(mu_byte: int) -> int:
    mu_byte = ~mu_byte & 0xFF
    sign = mu_byte & 0x80
    exponent = (mu_byte >> 4) & 0x07
    mantissa = mu_byte & 0x0F
    sample = _MULAW_DECODE_EXP_LUT[exponent] + (mantissa << (exponent + 3))
    return -sample if sign else sample


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    samples = (_mulaw_byte_to_linear(b) for b in mulaw_bytes)
    return b"".join(s.to_bytes(2, "little", signed=True) for s in samples)


def _rms(pcm16_bytes: bytes) -> float:
    if not pcm16_bytes:
        return 0.0
    count = len(pcm16_bytes) // 2
    total = sum(
        int.from_bytes(pcm16_bytes[i * 2 : i * 2 + 2], "little", signed=True) ** 2 for i in range(count)
    )
    return (total / count) ** 0.5


def _wrap_wav(pcm16_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm16_bytes)
    return buffer.getvalue()


class ClouderaWhisperSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.caii_stt_base_url,
            api_key=settings.caii_stt_api_key or "unused",
        )
        self._queue: asyncio.Queue[Transcript] = asyncio.Queue()
        self._pcm_buffer = bytearray()
        self._silence_ms = 0
        self._speech_ms = 0

    async def connect(self) -> None:
        return None  # no persistent connection -- each utterance is its own HTTP request

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        pcm16 = mulaw_to_pcm16(mulaw_bytes)
        self._pcm_buffer.extend(pcm16)

        if _rms(pcm16) >= SILENCE_RMS_THRESHOLD:
            self._speech_ms += CHUNK_MS
            self._silence_ms = 0
        else:
            self._silence_ms += CHUNK_MS

        buffered_ms = (len(self._pcm_buffer) // 2) / SAMPLE_RATE * 1000
        utterance_ready = self._speech_ms >= MIN_SPEECH_MS and self._silence_ms >= SILENCE_DURATION_MS
        force_flush = buffered_ms >= MAX_UTTERANCE_MS

        if self._speech_ms > 0 and (utterance_ready or force_flush):
            await self._flush()

    async def _flush(self) -> None:
        pcm_bytes = bytes(self._pcm_buffer)
        self._pcm_buffer.clear()
        self._speech_ms = 0
        self._silence_ms = 0
        if not pcm_bytes:
            return

        wav_bytes = _wrap_wav(pcm_bytes)
        try:
            response = await self._client.audio.transcriptions.create(
                model=settings.caii_stt_model_name,
                file=("utterance.wav", wav_bytes, "audio/wav"),
            )
        except Exception:
            return

        text = (getattr(response, "text", "") or "").strip()
        if text:
            await self._queue.put(Transcript(text=text, is_final=True))

    async def transcripts(self) -> AsyncIterator[Transcript]:
        while True:
            yield await self._queue.get()

    async def close(self) -> None:
        self._pcm_buffer.clear()
