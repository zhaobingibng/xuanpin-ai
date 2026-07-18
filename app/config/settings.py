"""Application settings powered by pydantic-settings."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "xuanpin-ai"
    app_env: str = "development"
    app_debug: bool = True
    app_log_level: str = "DEBUG"

    # Database (SQLite)
    db_path: str = "./storage/xuanpin.db"

    # AI / LLM
    ai_api_key: str = ""
    ai_model: str = "gpt-4"
    ai_base_url: str = "https://api.openai.com/v1"

    # Crawler
    crawler_user_agent: str = "XuanPinBot/1.0"
    crawler_timeout: int = 30
    crawler_max_retries: int = 3
    crawler_headless: bool = False
    crawler_cookie_dir: str = "./storage/cookies"
    crawler_storage_path: str = "./storage/crawler"

    # Storage
    storage_path: str = "./storage"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def async_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> AppSettings:
    """Return cached application settings instance."""
    return AppSettings()
