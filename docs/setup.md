# Setup

## Setting up the external services

1. **Twilio**: buy/reserve a voice-capable phone number in the
   [Twilio console](https://console.twilio.com). Note the Account SID and
   Auth Token — you'll set `TWILIO_AUTH_TOKEN` later. You'll point the
   number's "A call comes in" webhook at this app after it's deployed.
2. **Deepgram**: create an API key at [console.deepgram.com](https://console.deepgram.com).
3. **Cartesia**: create an API key at [play.cartesia.ai](https://play.cartesia.ai) — needed
   for TTS from the start; optional for STT until you switch `STT_PROVIDER`.
4. **Cloudera AI Inference Service**: in your CML workspace, deploy an
   instruct (or reasoning) model as a model endpoint (Cloudera AI Inference
   Service / Model Hub in the workbench UI — the exact catalog/CLI steps
   depend on your CDP version, so follow your workspace's current docs for
   "Cloudera AI Inference service"). Once deployed you'll have:
   - a base URL, typically shaped like
     `https://<domain>/namespaces/serving-default/endpoints/<endpoint-name>/v1`
     (OpenAI-compatible — the app uses the standard `openai` SDK against it)
   - a model name to pass in requests (e.g. `meta/llama-3.1-8b-instruct`)
   - an API key/token, if your endpoint requires one
5. **Optional — Whisper/Riva STT on Cloudera AI Inference Service**: if you
   already have a Whisper-family model deployed as its own endpoint (separate
   from the LLM above), you can use it instead of Deepgram/Cartesia for STT.
   See [`docs/architecture.md`](architecture.md) for how it's wired in and
   its tradeoffs.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/seed_customer_data.py
cp .env.example .env   # fill in your API keys
uvicorn app.main:app --reload --port 8090
```

For local testing with a real phone call, tunnel port 8090 (e.g. `ngrok http
8090`), set `PUBLIC_BASE_URL` to the ngrok HTTPS URL, and point the Twilio
number's webhook at `<ngrok-url>/voice`.

## Verifying it works before a real call

`scripts/simulate_call.py <sample.wav>` feeds a WAV file through the exact
`/media-stream` code path (fake Twilio events, real STT/TTS/LLM calls) to
prove STT → LLM → TTS works before ever placing a real call. Needs
`DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, and `CAII_*` set locally.

The `/dashboard/simulate` endpoint (and the `/dashboard` page's own trigger)
plays a canned call through the live-dashboard event feed with no Twilio
call required — useful for rehearsing a demo.
