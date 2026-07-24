import base64
import json
import uuid
from collections.abc import AsyncIterator

import websockets

from app.config import settings
from app.tts.base import TTSProvider

# output_format raw/pcm_mulaw/8000 is an exact match for Twilio's telephony
# audio format, so no resampling/transcoding is needed on either leg.
CARTESIA_TTS_URL = "wss://api.cartesia.ai/tts/websocket?cartesia_version=2026-03-01"


class CartesiaTTSProvider(TTSProvider):
    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        async with websockets.connect(
            CARTESIA_TTS_URL,
            additional_headers={"X-Api-Key": settings.cartesia_api_key},
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "model_id": settings.cartesia_tts_model_id,
                        "transcript": text,
                        "voice": {"mode": "id", "id": settings.cartesia_tts_voice_id},
                        "output_format": {
                            "container": "raw",
                            "encoding": "pcm_mulaw",
                            "sample_rate": 8000,
                        },
                        "context_id": str(uuid.uuid4()),
                    }
                )
            )
            async for raw in ws:
                message = json.loads(raw)
                msg_type = message.get("type")
                if msg_type == "chunk":
                    data = message.get("data")
                    if data:
                        yield base64.b64decode(data)
                elif msg_type == "error":
                    raise RuntimeError(f"Cartesia TTS error: {message}")
                elif msg_type == "done":
                    break
