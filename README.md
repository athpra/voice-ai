# Telecom Voice AI Agent Demo

A demo showing Cloudera AI powering a real-time voice agent: a caller dials a
phone number, their speech is transcribed live, enriched with their account
context (looked up by phone number), sent to a local LLM served by Cloudera
AI Inference Service, and the reply is spoken back to them — end to end,
orchestrated by a single [CML Application](https://docs.cloudera.com/machine-learning/cloud/applications/topics/ml-applications.html).

```
Caller
  │  PSTN call
  ▼
Twilio (Voice + bidirectional Media Streams)
  │  wss:// mulaw/8kHz audio, both directions
  ▼
CML Application (FastAPI, this repo)
  ├─ POST /voice          → TwiML: <Connect><Stream>
  ├─ WS   /media-stream    → orchestrates the call:
  │     1. look up caller by phone number → app/data/customers.db (mock data)
  │     2. stream audio → STT provider (Deepgram, or Cartesia, or a
  │        Whisper/Riva model on Cloudera AI Inference Service)
  │     3. on final transcript → LLM on Cloudera AI Inference Service
  │     4. reply text → TTS provider (Cartesia) → audio back to Twilio
  └─ GET  /health
```

By default only the STT/TTS/telephony legs are external APIs (Twilio,
Deepgram, Cartesia) — the call orchestration and the LLM run inside your
Cloudera AI workbench. If you switch `STT_PROVIDER=cloudera_whisper`, STT
runs on Cloudera AI too, leaving Cartesia TTS and Twilio telephony as the
only pieces still outside it (Whisper doesn't do TTS, so a separate TTS
service is still needed either way).

## What's real vs. mocked in this demo

- **Real**: telephony, STT, TTS, and the LLM call are all live external
  services once configured.
- **Mocked**: the "additional context about the caller" is a synthetic
  telecom customer dataset (`app/data/customers.db`, seeded by
  `scripts/seed_customer_data.py`) — no real customer/billing system is
  connected. Swap `app/data/customer_lookup.py` for a real data source later
  without touching the rest of the pipeline.

## Project layout

```
app/
  main.py                 FastAPI app: /voice, /media-stream, /health
  config.py                env-driven settings
  call_session.py          per-call state (history, caller context)
  twilio_gateway.py         TwiML + signature validation + call orchestration
  stt/                     STTProvider interface + Deepgram/Cartesia/Cloudera-Whisper implementations
  tts/                     TTSProvider interface + Cartesia implementation
  llm/cloudera_inference.py  OpenAI-compatible client against Cloudera AI Inference Service
  data/customer_lookup.py   phone-number lookup against the mock dataset
scripts/
  install_dependencies.py  pip install -r requirements.txt (CML bootstrap task)
  seed_customer_data.py    generates the mock customer dataset
  simulate_call.py         local smoke-test harness (see Verification below)
tests/
  test_customer_lookup.py
.project-metadata.yaml    CML AMP spec (env vars + tasks) for one-import deployment
run_app.py                 CML Application entrypoint (uvicorn on $CDSW_APP_PORT)
```

## STT providers: Deepgram, Cartesia, or Cloudera AI Inference Service (Whisper)

STT is behind `app/stt/base.py`'s `STTProvider` interface, with three
implementations. Switching is a config change, not a rewrite:

```
STT_PROVIDER=deepgram          # default — real-time streaming via Deepgram
STT_PROVIDER=cartesia          # real-time streaming via Cartesia (needs CARTESIA_API_KEY)
STT_PROVIDER=cloudera_whisper  # batch transcription via a Whisper/Riva model on Cloudera AI Inference Service
```

`deepgram_provider.py` is the active, exercised path. `cartesia_provider.py`
and `cloudera_whisper_provider.py` are real implementations (not stubs)
against each provider's documented API, but neither has been exercised
against a live account/endpoint yet — sanity-check them against a real call
once you have credentials.

**Why Cloudera-hosted Whisper works differently:** Deepgram and Cartesia
expose a websocket you stream audio into continuously, getting transcripts
back as you talk. Cloudera AI Inference Service's OpenAI-compatible API only
exposes the standard batch `/v1/audio/transcriptions` endpoint (whole audio
clip in, transcript out) — there's no streaming contract in that API shape,
regardless of how fast the underlying model serving is. So
`cloudera_whisper_provider.py` takes a different approach: it buffers each
utterance locally, uses simple energy-based silence detection (tunable
constants at the top of the file: `SILENCE_RMS_THRESHOLD`,
`SILENCE_DURATION_MS`, `MIN_SPEECH_MS`) to decide when the caller has
finished a sentence, then sends one HTTP request per turn instead of a
persistent connection. This means:

- Slightly higher latency per turn than Deepgram/Cartesia's live streaming
  (an utterance isn't sent until ~700ms of trailing silence is detected).
- No interim/partial transcripts — only a final one per utterance, which is
  all the rest of the pipeline needs anyway.
- STT runs entirely on Cloudera AI alongside the LLM — only TTS (Cartesia)
  and telephony (Twilio) remain external.

To use it, set `STT_PROVIDER=cloudera_whisper` plus `CAII_STT_BASE_URL`,
`CAII_STT_API_KEY`, and `CAII_STT_MODEL_NAME` (a separate endpoint/model from
the LLM's `CAII_BASE_URL`) — see `.env.example`. **Confirm the exact model
name your endpoint expects** before relying on it; it was left unset rather
than guessed.

## Setting up the external services

1. **Twilio**: buy/reserve a voice-capable phone number in the
   [Twilio console](https://console.twilio.com). Note the Account SID and
   Auth Token — you'll set `TWILIO_AUTH_TOKEN` later. You'll point the
   number's "A call comes in" webhook at this app after it's deployed.
2. **Deepgram**: create an API key at [console.deepgram.com](https://console.deepgram.com).
3. **Cartesia**: create an API key at [play.cartesia.ai](https://play.cartesia.ai) — needed
   for TTS from the start; optional for STT until you switch `STT_PROVIDER`.
4. **Cloudera AI Inference Service**: in your CML workspace, deploy
   **Llama 3.1 8B Instruct** as a model endpoint (Cloudera AI Inference
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
   See "STT providers" above for how it's wired in and its tradeoffs.

## Deploying to CML

This repo is structured as a CML Applied ML Prototype (AMP) via
`.project-metadata.yaml`, so it can be imported as a CML project in one step:

1. In your CML workspace, create a new project from this Git repo (push this
   directory to a repo CML can reach first).
2. CML will prompt for the environment variables declared in
   `.project-metadata.yaml`: `TWILIO_AUTH_TOKEN`, `DEEPGRAM_API_KEY`,
   `CARTESIA_API_KEY`, `CAII_BASE_URL`, `CAII_API_KEY`, `CAII_MODEL_NAME`.
   Leave `PUBLIC_BASE_URL` blank for now — the Application's URL isn't known
   until it's first started.
3. On import, CML runs the `install_dependencies` and `seed_customer_data`
   tasks, then starts the `Voice AI Agent` Application.
4. Once running, copy the Application's URL (shown in the CML UI, something
   like `https://voice-ai-agent.<workspace-domain>`). Set it as
   `PUBLIC_BASE_URL` in the Application's environment variables and restart
   it — this is required so Twilio signature validation and the `wss://`
   media-stream URL are computed correctly behind CML's proxy.
5. In the Twilio console, set the phone number's **"A call comes in"**
   webhook to `https://<same-domain>/voice` (HTTP POST).
6. Call the number.

**Note on websockets**: CML's application proxy supports websockets on TLS
workspaces out of the box. If your workspace runs without TLS, its external
load balancer needs websockets explicitly allowed on port 80 — check with
your CML admin if `/media-stream` connections fail to upgrade.

`bypass_authentication: true` is set on the Application because Twilio's
webhook can't complete CML's normal login flow — this makes `/voice` and
`/media-stream` reachable without a CML session. That's compensated by
Twilio request-signature validation in `twilio_gateway.validate_request`, so
requests not actually from your Twilio account are rejected.

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

## Verification

No live Twilio/Deepgram/Cartesia/CML credentials exist in the environment
this was built in, so what's been verified directly:

- `tests/test_customer_lookup.py` (passing): exact-match, formatted-number,
  local-number, unknown-caller, and missing-DB cases against a temp SQLite DB.
- `scripts/seed_customer_data.py` run successfully, producing 40 synthetic
  customers; spot-checked lookups by phone number in several formats.
- All modules byte-compile and the FastAPI app imports and wires up its
  routes (`/health`, `/voice`, `/media-stream`) cleanly.

What still needs your credentials to verify:

- `scripts/simulate_call.py <sample.wav>` — feeds a WAV file through the
  exact `/media-stream` code path (fake Twilio events, real Deepgram/Cartesia/
  CAII calls) to prove STT → LLM → TTS works before ever placing a real call.
  Needs `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, and `CAII_*` set locally.
- An actual phone call end-to-end, which needs the full CML deployment (step
  above) and a live Twilio number pointed at it.

## Known v1 limitations (by design, not oversights)

- No barge-in/interruption handling — the caller can't interrupt the agent
  mid-reply. Twilio's `clear` event supports this; add it as a fast-follow.
- The LLM reply is synthesized as one full TTS request rather than streamed
  sentence-by-sentence, trading a bit of latency for simplicity. Cartesia's
  `context_id` mechanism supports incremental streaming if you want to
  optimize this later.
- `cartesia_provider.py` (STT) and `cloudera_whisper_provider.py` are
  implemented against each provider's documented API but unverified against a
  live account/endpoint — confirm them once you have credentials.
- The silence-detection thresholds in `cloudera_whisper_provider.py`
  (`SILENCE_RMS_THRESHOLD`, `SILENCE_DURATION_MS`, `MIN_SPEECH_MS`) are
  heuristic starting points, not calibrated against a real phone line's noise
  floor — expect to tune them once you're testing with actual calls.
