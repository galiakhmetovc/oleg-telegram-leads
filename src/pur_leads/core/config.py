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
    web_session_cookie_name: str = "pur_session"
    web_cookie_secure: bool = False
    artifact_storage_path: Path = Path("./data/artifacts")
    backup_path: Path = Path("./artifacts/backups")
    zai_api_key: str | None = None
    catalog_llm_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    catalog_llm_model: str = "glm-5.1"
    catalog_llm_timeout_seconds: float = 60.0
    lead_llm_shadow_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    lead_llm_shadow_model: str = "glm-4.5-flash"
    lead_llm_shadow_timeout_seconds: float = 60.0

    model_config = SettingsConfigDict(env_prefix="PUR_", env_file=".env", extra="ignore")


def load_settings() -> AppSettings:
    return AppSettings()
