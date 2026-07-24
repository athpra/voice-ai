"""Local smoke-test harness for the STT -> LLM -> TTS pipeline, without a
real phone call or Twilio account.

Feeds a 16-bit PCM mono 8kHz WAV file through the exact /media-stream code
path (app.twilio_gateway.handle_media_stream), using fake Twilio 'connected'
/ 'start' / 'media' / 'stop' frames over an in-process test websocket. This
proves the pipeline logic (customer lookup, STT, LLM call, TTS) works before
ever touching real telephony -- but it still needs real DEEPGRAM_API_KEY,
CARTESIA_API_KEY, and CAII_* credentials set in the environment, since those
are live external services.

Usage:
    python scripts/simulate_call.py path/to/sample.wav [--caller +15550000001]

Record a short WAV yourself (16-bit PCM, mono, 8000 Hz) asking something like
"What's my data usage this month?" -- e.g. with `ffmpeg -i in.m4a -ar 8000
-ac 1 -sample_fmt s16 sample.wav`.
"""

import argparse
import base64
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FRAME_SAMPLES = 160  # 20ms @ 8000 Hz, matching Twilio's real chunking cadence


def _linear_to_mulaw_sample(sample: int) -> int:
    """Standard G.711 mu-law encoder for a single 16-bit signed PCM sample."""
    mulaw_max = 0x1FFF
    mulaw_bias = 33
    sign = 0x00
    if sample < 0:
        sample = -sample
        sign = 0x80
    sample += mulaw_bias
    if sample > mulaw_max:
        sample = mulaw_max
    exponent = 7
    exp_mask = 0x4000
    while exponent > 0 and not (sample & exp_mask):
        exponent -= 1
        exp_mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    sample_count = len(pcm_bytes) // 2
    samples = [int.from_bytes(pcm_bytes[i * 2 : i * 2 + 2], "little", signed=True) for i in range(sample_count)]
    return bytes(_linear_to_mulaw_sample(s) for s in samples)


def load_mulaw_frames(wav_path: str) -> list[bytes]:
    with wave.open(wav_path, "rb") as wav_file:
        if wav_file.getframerate() != 8000 or wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError(
                "Expected 16-bit PCM mono 8000 Hz WAV, got "
                f"{wav_file.getframerate()}Hz, {wav_file.getnchannels()}ch, "
                f"{wav_file.getsampwidth() * 8}-bit"
            )
        pcm_bytes = wav_file.readframes(wav_file.getnframes())

    mulaw_bytes = pcm16_to_mulaw(pcm_bytes)
    frame_bytes = FRAME_SAMPLES  # 1 byte per mulaw sample
    return [mulaw_bytes[i : i + frame_bytes] for i in range(0, len(mulaw_bytes), frame_bytes)]


def run(wav_path: str, caller_number: str) -> None:
    frames = load_mulaw_frames(wav_path)
    print(f"Loaded {len(frames)} audio frames ({len(frames) * 20}ms) from {wav_path}")

    reply_chunks: list[bytes] = []

    with TestClient(app) as client, client.websocket_connect("/media-stream") as ws:
        ws.send_text(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        ws.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "accountSid": "ACsimulated",
                        "streamSid": "MZsimulated",
                        "callSid": "CAsimulated",
                        "tracks": ["inbound"],
                        "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                        "customParameters": {"caller_number": caller_number},
                    },
                    "streamSid": "MZsimulated",
                }
            )
        )

        for i, frame in enumerate(frames):
            ws.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "media": {"track": "inbound", "chunk": str(i), "timestamp": str(i * 20), "payload": base64.b64encode(frame).decode()},
                        "streamSid": "MZsimulated",
                    }
                )
            )

        ws.send_text(json.dumps({"event": "stop", "stop": {"accountSid": "ACsimulated", "callSid": "CAsimulated"}, "streamSid": "MZsimulated"}))

        # Drain any reply audio/mark messages the server sends back.
        try:
            while True:
                raw = ws.receive_text()
                message = json.loads(raw)
                if message.get("event") == "media":
                    reply_chunks.append(base64.b64decode(message["media"]["payload"]))
                elif message.get("event") == "mark":
                    print(f"Received mark: {message['mark']['name']} ({len(reply_chunks)} audio chunks so far)")
        except Exception:
            pass

    if reply_chunks:
        out_path = Path("reply.mulaw")
        out_path.write_bytes(b"".join(reply_chunks))
        print(f"Wrote {len(reply_chunks)} reply audio chunks ({out_path.stat().st_size} bytes) to {out_path}")
    else:
        print("No reply audio received -- check DEEPGRAM_API_KEY/CARTESIA_API_KEY/CAII_* env vars and server logs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav_path", help="16-bit PCM mono 8000 Hz WAV file")
    parser.add_argument("--caller", default="+15550000001", help="Caller number to simulate (default matches a seeded mock customer)")
    args = parser.parse_args()
    run(args.wav_path, args.caller)
