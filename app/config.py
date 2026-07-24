import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    port: int = int(os.environ.get("CDSW_APP_PORT", os.environ.get("PORT", 8090)))
    public_base_url: str = ""  # e.g. https://voice-ai-agent.ml-xxxx.cloudera.site

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_validate_signature: bool = True

    # Provider selection
    stt_provider: str = "deepgram"  # "deepgram" | "cartesia"
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

    # Mock customer data
    customer_db_path: str = "app/data/customers.db"

    # Conversation shaping
    max_history_turns: int = 6


settings = Settings()
