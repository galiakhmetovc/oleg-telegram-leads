"""Programmatic Alembic helpers."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def alembic_config() -> Config:
    root = project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config


def upgrade_database(engine: Engine, revision: str = "head") -> None:
    config = alembic_config()
    with engine.begin() as connection:
        _ensure_alembic_version_capacity(connection)
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def _ensure_alembic_version_capacity(connection) -> None:  # noqa: ANN001
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(128) NOT NULL PRIMARY KEY
            )
            """
        )
    )
    connection.execute(
        text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    )
