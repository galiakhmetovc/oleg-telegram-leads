from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://pur_leads:pur_leads_dev_password@localhost:55433/pur_leads_v2"
    )
    environment: str = "development"

    model_config = SettingsConfigDict(env_prefix="PUR_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
