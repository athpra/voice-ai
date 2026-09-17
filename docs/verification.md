# Verification status and known limitations

## What's been verified directly

- `tests/test_customer_lookup.py`: exact-match, formatted-number,
  local-number, unknown-caller, and missing-DB cases against a temp SQLite DB.
- `tests/test_cloudera_inference.py`: reasoning-model handling (stripping
  `<think>` blocks, the thinking-off directive, recovering answers misfiled
  into `reasoning_content`, and fallback behavior on truncation).
- `scripts/seed_customer_data.py` run successfully, producing 40 synthetic
  customers; spot-checked lookups by phone number in several formats.
- All modules byte-compile and the FastAPI app imports and wires up its
  routes (`/health`, `/voice`, `/media-stream`, `/dashboard`) cleanly.

## What still needs live credentials to verify

- `scripts/simulate_call.py <sample.wav>` — needs `DEEPGRAM_API_KEY`,
  `CARTESIA_API_KEY`, and `CAII_*` set locally.
- An actual phone call end-to-end, which needs the full CML deployment (see
  [`deploy/cml-deployment.md`](../deploy/cml-deployment.md)) and a live
  Twilio number pointed at it.

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
- If `CAII_MODEL_NAME` points at a reasoning model, a turn that can't
  separate reasoning from the answer (see
  [`docs/architecture.md`](architecture.md#reasoning-models-on-the-llm-endpoint))
  falls back to a canned line instead of speaking scratch reasoning -- expect
  occasional generic replies until the model's thinking-off directive is
  confirmed to work.

## Known operational risk: `CAII_API_KEY` expiry

Observed in production: every greeting and reply silently fell back to the
generic/canned lines (`GENERIC_GREETING`, `LLM_FALLBACK_REPLY` in
`app/twilio_gateway.py`) for an entire call. The application logs showed why
-- both `generate_greeting()` and `generate_reply()` were throwing on every
turn:

```
openai.AuthenticationError: Error code: 401 - {'message': 'Token has expired', ...}
```

**Root cause:** `CAII_API_KEY` had expired. A JWT copied from a workbench
session had only a 1-hour gap between its `iat` and `exp` claims -- fine for
an interactive session, not for a long-running CML Application, which will
hit this the first time it's been up longer than the token's TTL.

**Symptom is silent, not a crash:** because `generate_greeting`/
`generate_reply` are called inside a `try/except Exception`, an expired
token degrades the whole call to canned fallback lines rather than
surfacing an obvious error to the caller or failing the Application --
worth checking the logs for `AuthenticationError` whenever replies look
suspiciously generic, before assuming it's a prompt or reasoning-model
issue like the ones above.

**Fix:** issue a fresh `CAII_API_KEY` and update it in the CML
Application's environment variables, then fully stop/start the Application.

**Unresolved as of this writing:** whether Cloudera AI Inference Service
offers a longer-lived/non-expiring service credential for this endpoint
(as opposed to a short-TTL session token), and/or whether the app should
add token-refresh logic -- `_client = AsyncOpenAI(...)` in
`app/llm/cloudera_inference.py` is constructed once at import time from a
static key, so even a longer-but-finite TTL will eventually need this.
Confirm the intended credential type with your CDP/CML admin before relying
on this in anything beyond a demo.
