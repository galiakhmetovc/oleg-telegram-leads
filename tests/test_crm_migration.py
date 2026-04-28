from sqlalchemy import inspect

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


def test_crm_migration_creates_memory_tables_and_indexes(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")

    upgrade_database(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "clients",
        "contacts",
        "client_objects",
        "client_interests",
        "client_assets",
        "opportunities",
        "support_cases",
        "contact_reasons",
        "touchpoints",
    }.issubset(tables)

    indexes = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in tables
    }
    assert "ix_clients_status_updated" in indexes["clients"]
    assert "ix_contacts_telegram_user_id" in indexes["contacts"]
    assert "ix_contacts_telegram_username" in indexes["contacts"]
    assert "ix_contacts_phone" in indexes["contacts"]
    assert "ix_client_interests_reactivation" in indexes["client_interests"]
    assert "ix_contact_reasons_queue" in indexes["contact_reasons"]
