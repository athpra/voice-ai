from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class TTSProvider(ABC):
    """Synthesizes text into mulaw/8000/mono audio chunks (raw bytes, not
    base64) ready to be wrapped into Twilio outbound media events."""

    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...
