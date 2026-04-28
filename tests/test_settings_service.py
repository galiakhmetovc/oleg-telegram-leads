import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.settings import settings_revisions_table
from pur_leads.services.settings import RawSecretValueError, SettingsService


@pytest.fixture
def settings_service(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield SettingsService(session)


def test_unknown_setting_returns_typed_default(settings_service):
    assert settings_service.get("telegram_worker_count") == 1
    assert settings_service.get("backup_sessions_enabled") is False


def test_set_new_setting_stores_typed_value(settings_service):
    settings_service.set(
        "telegram_worker_count",
        2,
        value_type="int",
        updated_by="admin",
        reason="test update",
    )

    assert settings_service.get("telegram_worker_count") == 2
    row = settings_service.repository.get("telegram_worker_count")
    assert row is not None
    assert row.value_json == 2
    assert row.value_type == "int"
    assert row.scope == "global"
    assert row.updated_by == "admin"


def test_update_setting_creates_revision_with_hashes(settings_service):
    settings_service.set("telegram_worker_count", 2, value_type="int", updated_by="admin")
    settings_service.set(
        "telegram_worker_count",
        3,
        value_type="int",
        updated_by="admin",
        reason="raise worker count",
    )

    revisions = (
        settings_service.session.execute(
            select(settings_revisions_table).where(
                settings_revisions_table.c.setting_key == "telegram_worker_count"
            )
        )
        .mappings()
        .all()
    )
    assert len(revisions) == 2
    latest = revisions[-1]
    assert latest.old_value_json == 2
    assert latest.new_value_json == 3
    assert len(latest.old_value_hash) == 64
    assert len(latest.new_value_hash) == 64
    assert latest.change_reason == "raise worker count"


def test_secret_setting_rejects_raw_secret_value(settings_service):
    with pytest.raises(RawSecretValueError):
        settings_service.set(
            "ai_api_key",
            "plain-secret-value",
            value_type="secret_ref",
            updated_by="admin",
        )

    settings_service.set(
        "ai_api_key",
        {"secret_ref_id": "secret-ref-1"},
        value_type="secret_ref",
        updated_by="admin",
    )

    assert settings_service.get("ai_api_key") == {"secret_ref_id": "secret-ref-1"}
