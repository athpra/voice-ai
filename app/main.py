import logging

from fastapi import FastAPI, Request, Response, WebSocket

from app.config import settings
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
    stream_url = _media_stream_url(request)
    twiml = build_twiml(caller_number, stream_url)
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await handle_media_stream(websocket)


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
