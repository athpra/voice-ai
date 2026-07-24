import asyncio
import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.call_session import CallSession
from app.config import settings
from app.data.customer_lookup import get_customer_context
from app.llm.cloudera_inference import generate_reply
from app.stt.factory import get_stt_provider
from app.tts.base import TTSProvider
from app.tts.factory import get_tts_provider

logger = logging.getLogger("voice_ai_agent")


def build_twiml(caller_number: str, stream_url: str) -> str:
    """Builds the TwiML that opens a bidirectional Media Stream. <Connect><Stream>
    (not <Start><Stream>) is required for the server to be able to send audio
    back to the caller."""
    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=stream_url)
    stream.parameter(name="caller_number", value=caller_number or "")
    response.append(connect)
    return str(response)


def validate_request(url: str, form_params: dict, signature: str) -> bool:
    if not settings.twilio_validate_signature:
        return True
    if not settings.twilio_auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set; rejecting request since signature validation is enabled")
        return False
    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(url, form_params, signature)


async def _speak(websocket: WebSocket, tts: TTSProvider, stream_sid: str, text: str) -> None:
    async for chunk in tts.synthesize(text):
        await websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": base64.b64encode(chunk).decode("ascii")},
                }
            )
        )
    await websocket.send_text(
        json.dumps({"event": "mark", "streamSid": stream_sid, "mark": {"name": "reply-complete"}})
    )


async def handle_media_stream(websocket: WebSocket) -> None:
    """Orchestrates one call end-to-end: Twilio audio in -> STT -> LLM (with
    caller context) -> TTS -> Twilio audio out. Runs until Twilio sends
    'stop' or the socket disconnects."""
    await websocket.accept()

    stream_sid: str | None = None
    session: CallSession | None = None
    stt = None
    tts = get_tts_provider()
    consumer_task: asyncio.Task | None = None

    async def consume_transcripts() -> None:
        assert stt is not None
        async for transcript in stt.transcripts():
            if not transcript.is_final or not transcript.text.strip():
                continue
            if session is None or stream_sid is None:
                continue
            logger.info("Caller (%s): %s", session.caller_number, transcript.text)
            session.add_turn("user", transcript.text, settings.max_history_turns)
            try:
                reply = await generate_reply(session, transcript.text)
            except Exception:
                logger.exception("LLM generation failed")
                continue
            session.add_turn("assistant", reply, settings.max_history_turns)
            logger.info("Agent: %s", reply)
            await _speak(websocket, tts, stream_sid, reply)

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            event = message.get("event")

            if event == "connected":
                continue

            if event == "start":
                start = message["start"]
                stream_sid = start["streamSid"]
                caller_number = start.get("customParameters", {}).get("caller_number", "")
                context = get_customer_context(caller_number)
                session = CallSession(
                    call_sid=start["callSid"],
                    stream_sid=stream_sid,
                    caller_number=caller_number,
                    customer_context=context,
                )
                logger.info(
                    "Call started: sid=%s caller=%s known_customer=%s",
                    session.call_sid,
                    caller_number,
                    bool(context),
                )
                stt = get_stt_provider()
                await stt.connect()
                consumer_task = asyncio.create_task(consume_transcripts())
                continue

            if event == "media":
                if stt is not None:
                    payload = message["media"]["payload"]
                    await stt.send_audio(base64.b64decode(payload))
                continue

            if event == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        if consumer_task is not None:
            consumer_task.cancel()
        if stt is not None:
            await stt.close()
        logger.info("Call ended: sid=%s", session.call_sid if session else "unknown")
