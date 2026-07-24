from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    is_final: bool


class STTProvider(ABC):
    """Streaming speech-to-text session for a single phone call.

    Audio arrives from Twilio as raw mulaw/8000/mono bytes (already
    base64-decoded by the caller) and is fed in via send_audio(). Transcripts
    come back through the transcripts() async generator, which runs until
    close() cancels it.
    """

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send_audio(self, mulaw_bytes: bytes) -> None: ...

    @abstractmethod
    def transcripts(self) -> AsyncIterator[Transcript]: ...

    @abstractmethod
    async def close(self) -> None: ...
