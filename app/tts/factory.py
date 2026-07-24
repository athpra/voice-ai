from app.config import settings
from app.tts.base import TTSProvider
from app.tts.cartesia_provider import CartesiaTTSProvider


def get_tts_provider() -> TTSProvider:
    provider = settings.tts_provider.lower()
    if provider == "cartesia":
        return CartesiaTTSProvider()
    raise ValueError(f"Unknown TTS_PROVIDER: {provider!r} (expected 'cartesia')")
