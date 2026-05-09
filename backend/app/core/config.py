from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://pur_leads:pur_leads_dev_password@localhost:55433/pur_leads_v2"
    )
    redis_url: str = "redis://localhost:6379/0"
    nlp_config_dir: Path = Path("config/nlp")
    cors_origins: str = "http://localhost:5173"
    environment: str = "development"
    code_version: str = "dev"
    process_role: str = "backend"
    auth_enabled: bool = True
    auth_username: str = "admin"
    auth_password: str = "pur-dev-password"
    auth_session_secret: str = "pur-dev-session-secret"
    auth_session_ttl_seconds: int = 60 * 60 * 24
    auth_cookie_name: str = "pur_session"
    public_base_url: str = "http://localhost:5173"
    project_docs_root: Path | None = None
    runtime_log_default_limit: int = 50
    runtime_log_max_limit: int = 200
    runtime_enrichment_event_retention_rows: int = 20000
    runtime_notification_outbox_retention_rows: int = 10000

    model_config = SettingsConfigDict(env_prefix="PUR_", env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
