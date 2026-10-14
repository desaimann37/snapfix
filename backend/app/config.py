"""Application settings, read from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    anthropic_api_key: str = ""
    anthropic_model_main: str = "claude-sonnet-5-5"
    anthropic_model_fast: str = "claude-haiku-5-5"
    llm_mode: str = "live"  # live | mock
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 2
    # Per-million-token prices, keyed by role so model names live only in the two settings above.
    price_main_input: float = 2.00
    price_main_output: float = 10.00
    price_fast_input: float = 0.10
    price_fast_output: float = 0.50

    # --- Data ---
    database_url: str = "postgresql+psycopg://snapfix:snapfix@localhost:5432/snapfix"
    upload_dir: str = str(BACKEND_DIR / "data" / "uploads")
    eval_results_dir: str = str(REPO_ROOT / "eval" / "results")

    # --- Embeddings ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_backend: str = "local"  # local | hash

    # --- Speech to text ---
    stt_fallback: str = "faster-whisper"  # faster-whisper | none

    # --- Notifications ---
    notifier: str = "console"  # console | slack | twilio
    slack_webhook_url: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    alert_to: str = ""

    # --- App ---
    admin_token: str = "change-me"
    frontend_origin: str = "http://localhost:3000"
    blur_faces: bool = False
    emergency_text: str = "If you smell gas or see fire/smoke, leave the area and call 911."
    max_upload_mb: int = 10
    scheduler_enabled: bool = True
    cluster_interval_s: int = 120
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
