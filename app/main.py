import asyncio
import logging

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.config import settings
from app.dashboard_events import broadcast, register, unregister
from app.dashboard_page import DASHBOARD_HTML
from app.twilio_gateway import build_twiml, handle_media_stream, validate_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_ai_agent")

app = FastAPI(title="Voice AI Agent Demo")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/voice")
async def voice(request: Request) -> Response:
    """Twilio's 'A Call Comes In' webhook. Returns TwiML that connects the
    call to our /media-stream websocket for bidirectional audio."""
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    validation_url = _public_url(request, "/voice")

    if not validate_request(validation_url, form_dict, signature):
        logger.warning("Rejected /voice request with invalid Twilio signature")
        return Response(status_code=403, content="Invalid Twilio signature")

    caller_number = form_dict.get("From", "")
    await broadcast({"type": "call_received", "caller_number": caller_number})
    stream_url = _media_stream_url(request)
    twiml = build_twiml(caller_number, stream_url)
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await handle_media_stream(websocket)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """A live view of the call pipeline for showing to customers -- lights up
    in real time as an actual call moves through Twilio -> STT -> LLM -> TTS."""
    html = DASHBOARD_HTML.replace("__DEMO_PHONE_NUMBER__", settings.demo_phone_number)
    return HTMLResponse(html)


@app.websocket("/dashboard-events")
async def dashboard_events(websocket: WebSocket) -> None:
    await register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        unregister(websocket)


@app.post("/dashboard/simulate")
async def dashboard_simulate() -> dict:
    """Plays a canned call through the dashboard's event feed, with no Twilio
    call required -- useful for rehearsing the demo or checking the dashboard
    looks right before a real call comes in."""
    asyncio.create_task(_run_simulation())
    return {"status": "started"}


async def _run_simulation() -> None:
    steps = [
        (0.0, {"type": "call_started", "call_sid": "CAsimulated000", "caller_number": "+1 (857) 757-8290"}),
        (0.6, {
            "type": "customer_identified", "known": True, "name": "Athul Prasad",
            "plan": "Unlimited Plus", "loyalty_tier": "Platinum", "customer_since_date": "2018-03-14",
        }),
        (1.4, {"type": "routing_to_llm"}),
        (2.6, {"type": "greeting_sent", "text": "Hi Athul, great to hear from you! It's a mild 61 degrees and clear out in San Francisco today -- and thank you for being a Platinum customer with us for 7 years."}),
        (2.7, {"type": "speaking"}),
        (5.2, {"type": "speaking_done"}),
        (6.4, {"type": "caller_said", "text": "I'm doing well, thanks! Can you tell me how much data I've used this month?"}),
        (6.6, {"type": "routing_to_llm"}),
        (7.8, {"type": "agent_reply", "text": "Of course -- you've used 42.3 of your 100 GB this month, so you've got plenty left."}),
        (7.9, {"type": "speaking"}),
        (10.0, {"type": "speaking_done"}),
        (11.5, {"type": "call_ended", "call_sid": "CAsimulated000"}),
    ]
    elapsed = 0.0
    for timestamp, event in steps:
        await asyncio.sleep(timestamp - elapsed)
        elapsed = timestamp
        await broadcast(event)


def _public_url(request: Request, path: str) -> str:
    if settings.public_base_url:
        return f"{settings.public_base_url.rstrip('/')}{path}"
    return str(request.url)


def _media_stream_url(request: Request) -> str:
    if settings.public_base_url:
        base = settings.public_base_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{base.rstrip('/')}/media-stream"
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return f"{scheme}://{request.url.netloc}/media-stream"
