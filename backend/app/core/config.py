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

    model_config = SettingsConfigDict(env_prefix="PUR_", env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
