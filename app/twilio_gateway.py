import asyncio
import base64
import json
import logging
import re

from fastapi import WebSocket, WebSocketDisconnect
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.call_session import CallSession
from app.config import settings
from app.dashboard_events import broadcast
from app.data.customer_lookup import get_customer_context
from app.llm.cloudera_inference import generate_greeting, generate_reply
from app.stt.factory import get_stt_provider
from app.tts.base import TTSProvider
from app.tts.factory import get_tts_provider
from app.weather import get_weather_blurb

GENERIC_GREETING = "Thanks for calling DemoTel! How can I help you today?"
LLM_FALLBACK_REPLY = "Sorry, I'm having a little trouble on my end -- could you say that again?"

# How long to wait after a "final" transcript chunk before treating it as a
# complete utterance. The STT provider's own is_final flag fires on a brief
# pause in speech, not on the caller actually finishing their sentence, so
# without this debounce the agent jumps in mid-sentence.
UTTERANCE_DEBOUNCE_SECONDS = 0.7

# If the caller trails off on a word like this ("...is there some way to"),
# it's almost certainly not a finished thought -- wait longer before treating
# it as complete, rather than applying the same short debounce to everything.
UTTERANCE_DEBOUNCE_EXTENDED_SECONDS = 1.6
_TRAILING_INCOMPLETE_WORDS = {
    # Articles, prepositions, and conjunctions that (almost) always need
    # something after them. Deliberately excludes pronouns like "it"/"you" --
    # those very often correctly end a complete sentence ("how are you",
    # "let me think about it"), so including them caused false positives.
    "a", "an", "the", "to", "for", "of", "in", "on", "with", "and", "but",
    "or", "so", "because", "if", "about",
}


def _sounds_incomplete(text: str) -> bool:
    words = text.strip().rstrip(".,!?").split()
    return bool(words) and words[-1].lower() in _TRAILING_INCOMPLETE_WORDS

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


_DECIMAL_RE = re.compile(r"(\d+)\.(\d+)")


def _speakable(text: str) -> str:
    """Spells out decimals ('42.3' -> '42 point 3') so the TTS engine reads
    them as words instead of mis-parsing the bare notation -- this is an
    input-formatting fix, not a TTS limitation."""
    return _DECIMAL_RE.sub(lambda m: f"{m.group(1)} point {m.group(2)}", text)


async def _speak(websocket: WebSocket, tts: TTSProvider, stream_sid: str, text: str) -> None:
    async for chunk in tts.synthesize(_speakable(text)):
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
    greeting_task: asyncio.Task | None = None
    # Greeting generation and turn processing both do "add user turn ->
    # await the LLM -> add assistant turn"; without serializing them, a
    # caller who starts talking the instant the call connects could interleave
    # writes to session.history mid-flight and break the strict user/assistant
    # alternation the model requires.
    history_lock = asyncio.Lock()

    async def consume_transcripts() -> None:
        assert stt is not None
        pending_text = ""
        last_chunk_at = 0.0

        async def process_utterance(text: str) -> None:
            if not text or session is None or stream_sid is None:
                return
            logger.info("Caller (%s): %s", session.caller_number, text)
            await broadcast({"type": "caller_said", "text": text})
            async with history_lock:
                session.add_turn("user", text, settings.max_history_turns)
                await broadcast({"type": "routing_to_llm"})
                try:
                    reply = await generate_reply(session)
                except Exception:
                    logger.exception("LLM generation failed")
                    reply = LLM_FALLBACK_REPLY
                session.add_turn("assistant", reply, settings.max_history_turns)
            logger.info("Agent: %s", reply)
            await broadcast({"type": "agent_reply", "text": reply})
            await broadcast({"type": "speaking"})
            await _speak(websocket, tts, stream_sid, reply)
            await broadcast({"type": "speaking_done"})

        async def debounce_loop() -> None:
            # A single persistent loop (rather than cancel-and-restart tasks
            # per chunk) avoids a race where an in-flight utterance gets
            # cancelled after it has already recorded a "user" turn but
            # before the matching "assistant" reply is added, which breaks
            # the strict user/assistant alternation the model requires.
            nonlocal pending_text
            while True:
                await asyncio.sleep(0.15)
                if not pending_text:
                    continue
                required_wait = (
                    UTTERANCE_DEBOUNCE_EXTENDED_SECONDS
                    if _sounds_incomplete(pending_text)
                    else UTTERANCE_DEBOUNCE_SECONDS
                )
                if (asyncio.get_event_loop().time() - last_chunk_at) >= required_wait:
                    text, pending_text = pending_text.strip(), ""
                    await process_utterance(text)

        loop_task = asyncio.create_task(debounce_loop())
        try:
            async for transcript in stt.transcripts():
                if not transcript.is_final or not transcript.text.strip():
                    continue
                if session is None or stream_sid is None:
                    continue
                pending_text = f"{pending_text} {transcript.text}".strip()
                last_chunk_at = asyncio.get_event_loop().time()
        finally:
            loop_task.cancel()

    async def send_greeting() -> None:
        assert session is not None and stream_sid is not None
        context = session.customer_context
        weather_blurb = await get_weather_blurb(context.get("city", "")) if context else None
        async with history_lock:
            if context:
                await broadcast({"type": "routing_to_llm"})
                try:
                    greeting = await generate_greeting(session, weather_blurb)
                except Exception:
                    logger.exception("Greeting generation failed")
                    greeting = GENERIC_GREETING
            else:
                greeting = GENERIC_GREETING
            # The model requires the first message after "system" to be
            # "user", so the call-connecting itself is recorded as a
            # synthetic user turn before the greeting -- otherwise every
            # later real turn fails with "roles must alternate user/assistant/...".
            session.add_turn("user", "(Call connected.)", settings.max_history_turns)
            session.add_turn("assistant", greeting, settings.max_history_turns)
        logger.info("Agent (greeting): %s", greeting)
        await broadcast({"type": "greeting_sent", "text": greeting})
        await broadcast({"type": "speaking"})
        await _speak(websocket, tts, stream_sid, greeting)
        await broadcast({"type": "speaking_done"})

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
                await broadcast({"type": "call_started", "call_sid": session.call_sid, "caller_number": caller_number})
                await broadcast(
                    {
                        "type": "customer_identified",
                        "known": bool(context),
                        "name": context.get("full_name"),
                        "plan": context.get("plan_name"),
                        "loyalty_tier": context.get("loyalty_tier"),
                        "customer_since_date": context.get("customer_since_date"),
                    }
                )
                stt = get_stt_provider()
                await stt.connect()
                consumer_task = asyncio.create_task(consume_transcripts())
                greeting_task = asyncio.create_task(send_greeting())
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
        if greeting_task is not None:
            greeting_task.cancel()
        if stt is not None:
            await stt.close()
        logger.info("Call ended: sid=%s", session.call_sid if session else "unknown")
        await broadcast({"type": "call_ended", "call_sid": session.call_sid if session else None})
