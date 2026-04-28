from sqlalchemy import inspect

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


def test_telegram_source_migration_creates_source_tables(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    tables = set(inspect(engine).get_table_names())
    assert {
        "userbot_accounts",
        "monitored_sources",
        "source_access_checks",
        "source_preview_messages",
        "source_messages",
        "sender_profiles",
        "message_context_links",
    }.issubset(tables)


def test_source_messages_use_canonical_message_identity(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("source_messages")}
    unique_constraints = inspector.get_unique_constraints("source_messages")

    assert {
        "id",
        "monitored_source_id",
        "raw_source_id",
        "telegram_message_id",
        "archive_pointer_id",
        "is_archived_stub",
        "text_archived",
        "caption_archived",
        "metadata_archived",
    }.issubset(columns)
    assert any(
        constraint["column_names"] == ["monitored_source_id", "telegram_message_id"]
        for constraint in unique_constraints
    )


def test_monitored_sources_have_onboarding_and_checkpoint_fields(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("monitored_sources")}
    assert {
        "source_kind",
        "source_purpose",
        "status",
        "start_mode",
        "checkpoint_message_id",
        "checkpoint_date",
        "assigned_userbot_account_id",
        "lead_detection_enabled",
        "catalog_ingestion_enabled",
    }.issubset(columns)
