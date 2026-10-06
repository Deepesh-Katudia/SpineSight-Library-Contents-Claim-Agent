"""Runtime configuration, loaded from the repo-root .env (or the process environment)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", API_ROOT / ".env"),
        extra="ignore",
    )

    primary_country: str = "IN"
    primary_currency: str = "INR"
    second_country: str = "US"
    second_currency: str = "USD"
    appraisal_threshold: float = 10000.0

    gemini_api_key: str = ""
    gemini_live_model: str = "gemini-3.8-live"

    openrouter_api_key: str = ""
    openrouter_vision_model: str = "google/gemini-3.8-flash"
    openrouter_text_model: str = "google/gemini-3.5-flash-lite"

    google_books_api_key: str = ""
    ebay_client_id: str = ""
    ebay_client_secret: str = ""

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "frames"
    mongodb_uri: str = ""
    mongodb_db: str = "spinesight"

    web_origin: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    max_open_sweeps: int = 20
    max_frames_per_sweep: int = 1500
    data_dir: Path = API_ROOT / "data"

    # Honesty thresholds: below these a book stays "unidentified" rather than guessed.
    min_legibility: float = 0.6
    min_catalog_match: float = 0.82


@lru_cache
def get_settings() -> Settings:
    return Settings()
