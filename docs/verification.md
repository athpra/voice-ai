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
