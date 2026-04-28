"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Environment-backed application settings."""

    database_path: Path = Path("./data/pur-leads.sqlite3")
    log_level: str = "INFO"
    web_host: str = "127.0.0.1"
    web_port: int = 8000

    model_config = SettingsConfigDict(env_prefix="PUR_", env_file=".env", extra="ignore")


def load_settings() -> AppSettings:
    return AppSettings()
