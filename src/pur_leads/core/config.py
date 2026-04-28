"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Environment-backed application settings."""

    database_path: Path = Path("./data/pur-leads.sqlite3")
    log_level: str = "INFO"
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    web_session_duration_hours: int = 24 * 14
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str | None = None
    telegram_bot_token: str | None = None

    model_config = SettingsConfigDict(env_prefix="PUR_", env_file=".env", extra="ignore")


def load_settings() -> AppSettings:
    return AppSettings()
