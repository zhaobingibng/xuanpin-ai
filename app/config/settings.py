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

    # AI / LLM (OpenAI-compatible: DeepSeek / Qwen / GPT)
    ai_api_key: str = ""
    ai_model: str = "deepseek-chat"
    ai_base_url: str = "https://api.deepseek.com"

    # Browser
    browser_headless: bool = True
    browser_timeout: int = 30000
    browser_user_agent: str = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    browser_user_data_dir: str = "./storage/browser_profile"
    browser_persistent: bool = True

    # Crawler
    crawler_user_agent: str = "XuanPinBot/1.0"
    crawler_timeout: int = 30
    crawler_max_retries: int = 3
    crawler_retry: int = 3
    crawler_retry_times: int = 3
    crawler_retry_delay: int = 5
    crawler_headless: bool = False
    cookie_dir: str = "./storage/cookies"
    login_check_timeout: int = 15
    crawler_storage_path: str = "./storage/crawler"

    # Storage
    storage_path: str = "./storage"

    # Daily Pipeline
    daily_crawl_hour: int = 8
    daily_selection_enabled: bool = True
    crawl_keywords: list[str] = [
        "蓝牙耳机",
        "手机配件",
        "家居用品",
        "收纳神器",
        "宠物用品",
        "女装",
        "美妆",
    ]
    daily_crawl_limit: int = 100
    crawl_platforms: list[str] = ["xiaohongshu"]

    # Xiaohongshu anti-bot cooldown (seconds between keyword crawls)
    xhs_cooldown_min: int = 60
    xhs_cooldown_max: int = 180

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
