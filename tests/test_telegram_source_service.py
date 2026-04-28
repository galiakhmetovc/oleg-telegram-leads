import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.services.telegram_sources import (
    CheckpointResetRequiresConfirmation,
    TelegramSourceService,
)


@pytest.fixture
def source_service(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        yield TelegramSourceService(session), session


def test_create_draft_source_defaults_to_live_lead_monitoring(source_service):
    service, session = source_service

    source = service.create_draft("@example_chat", added_by="admin")

    assert source.input_ref == "@example_chat"
    assert source.username == "example_chat"
    assert source.source_kind == "telegram_supergroup"
    assert source.source_purpose == "lead_monitoring"
    assert source.status == "draft"
    assert source.start_mode == "from_now"
    assert source.historical_backfill_policy == "retro_web_only"
    assert source.lead_detection_enabled is True
    assert source.catalog_ingestion_enabled is False

    audit_row = session.execute(select(audit_log_table)).mappings().one()
    assert audit_row["action"] == "monitored_source.create"
    assert audit_row["entity_id"] == source.id


def test_catalog_ingestion_source_sets_catalog_flags(source_service):
    service, _session = source_service

    source = service.create_draft(
        "https://t.me/purmaster",
        purpose="catalog_ingestion",
        added_by="admin",
    )

    assert source.username == "purmaster"
    assert source.source_kind == "telegram_channel"
    assert source.source_purpose == "catalog_ingestion"
    assert source.lead_detection_enabled is False
    assert source.catalog_ingestion_enabled is True


def test_status_transitions_to_active(source_service):
    service, _session = source_service
    source = service.create_draft("@example_chat", added_by="admin")

    checking = service.set_status(source.id, "checking_access", actor="admin")
    preview = service.set_status(source.id, "preview_ready", actor="admin")
    active = service.activate(source.id, actor="admin")

    assert checking.status == "checking_access"
    assert preview.status == "preview_ready"
    assert active.status == "active"
    assert active.activated_by == "admin"
    assert active.activated_at is not None


def test_checkpoint_reset_requires_confirmation(source_service):
    service, _session = source_service
    source = service.create_draft("@example_chat", added_by="admin")

    with pytest.raises(CheckpointResetRequiresConfirmation):
        service.reset_checkpoint(source.id, message_id=100, actor="admin", confirm=False)

    updated = service.reset_checkpoint(source.id, message_id=100, actor="admin", confirm=True)

    assert updated.checkpoint_message_id == 100
    assert updated.checkpoint_date is not None
