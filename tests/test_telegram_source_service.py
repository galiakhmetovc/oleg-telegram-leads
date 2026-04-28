import pytest
from datetime import datetime

from sqlalchemy import insert, select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import audit_log_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import source_preview_messages_table
from pur_leads.services.telegram_sources import (
    ActivationRequiresPreview,
    CheckpointResetRequiresConfirmation,
    TelegramSourceService,
)
from pur_leads.services.userbots import UserbotAccountService


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


def test_source_onboarding_controls_enqueue_jobs_and_list_detail(source_service):
    service, session = source_service
    source = service.create_draft("@example_chat", added_by="admin")

    access_job = service.request_access_check(source.id, actor="admin")
    preview_ready = service.set_status(source.id, "preview_ready", actor="system")
    _insert_preview_message(session, preview_ready.id)
    preview_job = service.request_preview(source.id, actor="admin", limit=5)
    detail = service.get_source_detail(source.id)
    rows = service.list_sources()

    assert rows[0].id == source.id
    assert access_job.job_type == "check_source_access"
    assert access_job.monitored_source_id == source.id
    assert access_job.idempotency_key == f"source:{source.id}:check_access"
    assert preview_job.job_type == "fetch_source_preview"
    assert preview_job.payload_json == {"limit": 5, "requested_by": "admin"}
    assert detail.source.status == "preview_ready"
    assert len(detail.preview_messages) == 1
    assert detail.preview_messages[0].text == "preview text"
    assert [job.job_type for job in detail.jobs] == ["fetch_source_preview", "check_source_access"]

    source_row = session.execute(select(scheduler_jobs_table)).mappings().first()
    assert source_row is not None


def test_new_sources_and_jobs_use_default_active_userbot(source_service):
    service, session = source_service
    userbot = UserbotAccountService(session).create_account(
        display_name="Main userbot",
        session_name="main",
        session_path="/secure/main.session",
        actor="admin",
    )

    source = service.create_draft("@example_chat", added_by="admin")
    access_job = service.request_access_check(source.id, actor="admin")
    service.set_status(source.id, "preview_ready", actor="system")
    preview_job = service.request_preview(source.id, actor="admin", limit=5)
    _activated, poll_job = service.activate_from_web(source.id, actor="admin")

    assert source.assigned_userbot_account_id == userbot.id
    assert access_job.userbot_account_id == userbot.id
    assert preview_job.userbot_account_id == userbot.id
    assert poll_job.userbot_account_id == userbot.id


def test_activate_from_web_requires_preview_and_enqueues_poll(source_service):
    service, session = source_service
    source = service.create_draft("@example_chat", added_by="admin")

    try:
        service.activate_from_web(source.id, actor="admin")
    except ActivationRequiresPreview as exc:
        assert "preview_ready" in str(exc)
    else:
        raise AssertionError("activation without preview should fail")

    service.set_status(source.id, "preview_ready", actor="system")
    activated, poll_job = service.activate_from_web(source.id, actor="admin")
    paused = service.pause(source.id, actor="admin")

    assert activated.status == "active"
    assert activated.next_poll_at is not None
    assert poll_job.job_type == "poll_monitored_source"
    assert poll_job.monitored_source_id == source.id
    assert poll_job.idempotency_key == f"source:{source.id}:poll"
    assert paused.status == "paused"

    jobs = session.execute(select(scheduler_jobs_table)).mappings().all()
    assert [job["job_type"] for job in jobs] == ["poll_monitored_source"]


def _insert_preview_message(session, source_id: str) -> None:
    session.execute(
        insert(source_preview_messages_table).values(
            id="preview-1",
            monitored_source_id=source_id,
            access_check_id=None,
            telegram_message_id=10,
            message_date=datetime(2026, 4, 28, 12, 0, 0),
            sender_display="Sender",
            text="preview text",
            caption=None,
            has_media=False,
            media_metadata_json=None,
            sort_order=0,
            created_at=datetime(2026, 4, 28, 12, 0, 0),
        )
    )
    session.commit()
