import asyncio
import json
from collections.abc import AsyncIterator

import websockets

from app.config import settings
from app.stt.base import STTProvider, Transcript

# encoding/sample_rate/channels must match the mulaw/8000/mono audio Twilio
# sends over Media Streams. interim_results gives fast partials for logging;
# endpointing marks an utterance final after ~300ms of silence.
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw&sample_rate=8000&channels=1"
    "&punctuate=true&interim_results=true&endpointing=300&smart_format=true"
)


class DeepgramSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._queue: asyncio.Queue[Transcript] = asyncio.Queue()
        self._recv_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            DEEPGRAM_URL,
            additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
        )
        self._recv_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            message = json.loads(raw)
            if message.get("type") != "Results":
                continue
            alternatives = message.get("channel", {}).get("alternatives", [])
            if not alternatives:
                continue
            text = alternatives[0].get("transcript", "")
            if not text:
                continue
            is_final = bool(message.get("is_final") or message.get("speech_final"))
            await self._queue.put(Transcript(text=text, is_final=is_final))

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(mulaw_bytes)

    async def transcripts(self) -> AsyncIterator[Transcript]:
        while True:
            yield await self._queue.get()

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except websockets.exceptions.ConnectionClosed:
                pass
        if self._recv_task is not None:
            self._recv_task.cancel()
