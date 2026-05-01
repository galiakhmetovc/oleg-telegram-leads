"""Database engine configuration."""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url


def create_database_engine(
    *,
    database_url: str | None = None,
    sqlite_path: str | Path | None = None,
) -> Engine:
    """Create the operational database engine.

    Postgres is the production database. SQLite remains available as a local
    development/test fallback and for existing tests while the product migrates.
    """

    if database_url:
        return create_engine(database_url, future=True, pool_pre_ping=True)
    if sqlite_path is None:
        raise ValueError("sqlite_path is required when database_url is not configured")
    return create_sqlite_engine(sqlite_path)


def is_postgres_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "postgresql"


def create_sqlite_engine(db_path: str | Path) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30}, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.close()

    return engine
