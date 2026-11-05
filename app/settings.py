from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/intake.sqlite"
    redis_url: str = "redis://localhost:6379/0"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    fetch_interval_minutes: int = 30
    send_mode: str = "confirmation"
    data_dir: str = "data"
    log_level: str = "INFO"
    config_dir: str = ""
    http_timeout_seconds: float = 25
    http_min_interval_seconds: float = 2
    http_max_retries: int = 3
    user_agent: str = "QoraIntake/0.1 (public feed reader; no bid submission)"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    digest_hour_utc: int = 6

    @property
    def config_path(self) -> Path:
        if self.config_dir:
            return Path(self.config_dir)
        return ROOT / "config"

    @property
    def effective_send_mode(self) -> str:
        # Этот срез умеет только режим подтверждения. Автоотправки нет.
        return "confirmation"


@lru_cache
def get_settings() -> Settings:
    return Settings()
