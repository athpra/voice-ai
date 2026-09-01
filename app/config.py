import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    port: int = int(os.environ.get("CDSW_APP_PORT", os.environ.get("PORT", 8090)))
    public_base_url: str = ""  # e.g. https://voice-ai-agent.ml-xxxx.cloudera.site
    demo_phone_number: str = ""  # shown on the /dashboard idle screen only, e.g. +1 (256) 676-9589

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_validate_signature: bool = True

    # Provider selection
    stt_provider: str = "deepgram"  # "deepgram" | "cartesia" | "cloudera_whisper"
    tts_provider: str = "cartesia"  # "cartesia"

    # Deepgram
    deepgram_api_key: str = ""

    # Cartesia
    cartesia_api_key: str = ""
    cartesia_tts_voice_id: str = "e07c00bc-4134-4eae-9ea4-1a55fb45746b"
    cartesia_tts_model_id: str = "sonic-3"
    cartesia_stt_model: str = "ink-whisper"

    # Cloudera AI Inference Service (OpenAI-compatible)
    caii_base_url: str = ""  # e.g. https://<domain>/namespaces/serving-default/endpoints/<endpoint>/v1
    caii_api_key: str = ""
    caii_model_name: str = "meta/llama-3.1-8b-instruct"
    # Reasoning ("thinking") models -- e.g. NVIDIA Nemotron -- emit a
    # <think>...</think> block before their answer. That's pure latency and
    # wasted tokens for a phone call, and if the block gets truncated by
    # max_tokens the caller ends up hearing the model's scratch reasoning.
    # Set this to the directive your model uses to disable it and it's folded
    # into the front of the system prompt: "detailed thinking off" for
    # Llama-Nemotron, "/no_think" for Nemotron Nano v2. Leave blank for
    # non-reasoning models.
    caii_thinking_directive: str = ""
    # Reasoning models need room to finish thinking (and emit the closing
    # </think> we strip on) before the answer -- a tight cap just truncates
    # them mid-thought. Generous by design; a real 1-2 sentence reply stops
    # well short of it. When a reasoning model still blows past this without
    # reaching an answer, the turn falls back to a canned line.
    caii_max_output_tokens: int = 1024

    # Cloudera AI Inference Service -- Whisper/Riva STT endpoint (separate
    # deployment from the LLM above, so it gets its own base URL/model name)
    caii_stt_base_url: str = ""  # e.g. https://<domain>/namespaces/serving-default/endpoints/<whisper-endpoint>/v1
    caii_stt_api_key: str = ""
    caii_stt_model_name: str = "nvidia/riva-asr/whisper"

    # Mock customer data
    customer_db_path: str = "app/data/customers.db"

    # Conversation shaping
    max_history_turns: int = 6


settings = Settings()
