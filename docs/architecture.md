# Architecture

See [`assets/architecture.svg`](../assets/architecture.svg) for the visual
diagram. This page covers the same pipeline in more detail.

**On vendors**: the diagram and this doc name specific providers (Twilio,
Deepgram, Cartesia) because that's what's actually wired up in this repo, but
none of them are architecturally required. The telephony leg, STT, and TTS
are each a distinct integration point in the call flow below — Twilio is the
reference telephony integration this demo ships with, not a hard dependency.
STT and TTS already sit behind provider interfaces (`app/stt/base.py`,
`app/tts/base.py`) so swapping those is a matter of adding an implementation,
not restructuring the app; the same swap for telephony would mean carving a
`TelephonyGateway`-style interface out of `app/twilio_gateway.py`, which
today mixes Twilio's specific protocol (TwiML, its signature scheme, its
media-stream JSON/mulaw framing) together with the STT→LLM→TTS orchestration
logic. That's a real but separate piece of work from what's described here.

## Call flow

1. The telephony provider (Twilio in this reference implementation) receives
   the PSTN call and posts to `POST /voice`, which returns TwiML connecting
   the call to this app's `/media-stream` websocket for bidirectional audio
   (mulaw/8kHz).
2. On connect, the caller's phone number is looked up in a mock telecom
   customer dataset (`app/data/customers.db`) to pull account context into
   the conversation.
3. Caller audio is streamed to the configured STT provider; on each final
   transcript, the conversation (system prompt + history + new turn) is sent
   to an LLM served by Cloudera AI Inference Service.
4. The reply text is sent to the TTS provider (Cartesia by default) and the
   resulting audio is streamed back to the caller over the same media-stream
   socket.
5. A separate `GET /dashboard` + `WS /dashboard-events` pair drives a live
   view of the pipeline for demo purposes, fed by the same call events.

By default only the telephony, STT, and TTS legs are external APIs (Twilio,
Deepgram, Cartesia in this reference configuration) — the call orchestration
and the LLM run inside your Cloudera AI workbench. If you switch
`STT_PROVIDER=cloudera_whisper`, STT runs on Cloudera AI too, leaving TTS and
telephony as the only pieces still outside it (Whisper doesn't do TTS, so a
separate TTS service is still needed either way).

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
  main.py                    FastAPI app: /voice, /media-stream, /health, /dashboard
  config.py                  env-driven settings
  call_session.py            per-call state (history, caller context)
  twilio_gateway.py          TwiML + signature validation + call orchestration
  dashboard_page.py          live-dashboard HTML
  dashboard_events.py        websocket fan-out for dashboard events
  stt/                       STTProvider interface + Deepgram/Cartesia/Cloudera-Whisper implementations
  tts/                       TTSProvider interface + Cartesia implementation
  llm/cloudera_inference.py  OpenAI-compatible client against Cloudera AI Inference Service
  data/customer_lookup.py    phone-number lookup against the mock dataset
scripts/
  install_dependencies.py    pip install -r requirements.txt (CML bootstrap task)
  seed_customer_data.py      generates the mock customer dataset
  simulate_call.py           local smoke-test harness (see docs/setup.md)
tests/
  test_customer_lookup.py
  test_cloudera_inference.py
.project-metadata.yaml       CML AMP spec (env vars + tasks) -- must stay at repo root; CML reads it there
run_app.py                   CML Application entrypoint (uvicorn on $CDSW_APP_PORT) -- must stay at repo root
```

`.project-metadata.yaml` and `run_app.py` are CML's own deployment
descriptors and are read from the repository root by CML tooling, so they
are not relocated into `deploy/` — see [`deploy/cml-deployment.md`](../deploy/cml-deployment.md)
for how they drive the actual deployment.

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

To use it, set `STT_PROVIDER=cloudera_whisper` plus `CAII_STT_BASE_URL` and
`CAII_STT_API_KEY` (a separate endpoint from the LLM's `CAII_BASE_URL`) — see
`.env.example`. `CAII_STT_MODEL_NAME` defaults to `nvidia/riva-asr/whisper`;
override it if your deployment registers the model under a different name.

## Reasoning models on the LLM endpoint

`CAII_MODEL_NAME` can point at a reasoning model (e.g. an NVIDIA Nemotron
variant) instead of a plain instruct model. Reasoning models "think" before
answering, which adds latency and can leak scratch reasoning into a voice
reply if not handled. `app/llm/cloudera_inference.py` accounts for this:

- `CAII_THINKING_DIRECTIVE` is folded into the system prompt to ask the model
  to skip reasoning (e.g. `detailed thinking off`, or `/no_think` on some
  model families) — the right string is model-specific.
- `CAII_MAX_OUTPUT_TOKENS` gives a reasoning model enough room to finish
  thinking and reach an answer instead of being cut off mid-thought.
- Reasoning wrapped in `<think>...</think>` (or terminated by a bare
  `</think>`) is stripped before the reply is spoken; if a model exhausts its
  token budget without ever producing an answer, the turn falls back to a
  canned line rather than speaking raw reasoning.
