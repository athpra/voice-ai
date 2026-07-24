import asyncio
import json
from collections.abc import AsyncIterator

import websockets

from app.config import settings
from app.stt.base import STTProvider, Transcript

# Real implementation against Cartesia's documented STT websocket API
# (wss://api.cartesia.ai/stt/websocket, model=ink-whisper, pcm_mulaw/8000).
# Not yet exercised against a live Cartesia account -- verify once
# CARTESIA_API_KEY is available, then switch via STT_PROVIDER=cartesia.
CARTESIA_STT_URL = (
    "wss://api.cartesia.ai/stt/websocket"
    "?model={model}&encoding=pcm_mulaw&sample_rate=8000&cartesia_version=2026-03-01"
)


class CartesiaSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._queue: asyncio.Queue[Transcript] = asyncio.Queue()
        self._recv_task: asyncio.Task | None = None

    async def connect(self) -> None:
        url = CARTESIA_STT_URL.format(model=settings.cartesia_stt_model)
        self._ws = await websockets.connect(
            url,
            additional_headers={"X-API-Key": settings.cartesia_api_key},
        )
        self._recv_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            message = json.loads(raw)
            if message.get("type") != "transcript":
                continue
            text = message.get("text", "")
            if not text:
                continue
            await self._queue.put(Transcript(text=text, is_final=bool(message.get("is_final"))))

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(mulaw_bytes)

    async def transcripts(self) -> AsyncIterator[Transcript]:
        while True:
            yield await self._queue.get()

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send("finalize")
                await self._ws.send("close")
                await self._ws.close()
            except websockets.exceptions.ConnectionClosed:
                pass
        if self._recv_task is not None:
            self._recv_task.cancel()
