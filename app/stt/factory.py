from app.config import settings
from app.stt.base import STTProvider
from app.stt.cartesia_provider import CartesiaSTTProvider
from app.stt.cloudera_whisper_provider import ClouderaWhisperSTTProvider
from app.stt.deepgram_provider import DeepgramSTTProvider


def get_stt_provider() -> STTProvider:
    provider = settings.stt_provider.lower()
    if provider == "deepgram":
        return DeepgramSTTProvider()
    if provider == "cartesia":
        return CartesiaSTTProvider()
    if provider == "cloudera_whisper":
        return ClouderaWhisperSTTProvider()
    raise ValueError(
        f"Unknown STT_PROVIDER: {provider!r} (expected 'deepgram', 'cartesia', or 'cloudera_whisper')"
    )
