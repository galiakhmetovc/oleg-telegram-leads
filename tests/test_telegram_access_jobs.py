from datetime import datetime

import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramMessage,
)
from pur_leads.models.audit import operational_events_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_access_checks_table,
    source_preview_messages_table,
)
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.telegram_access import TelegramAccessWorker


class FakeTelegramClient:
    def __init__(self, access_status: str = "succeeded") -> None:
        self.access_status = access_status

    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        return ResolvedTelegramSource(
            input_ref=input_ref,
            source_kind="telegram_channel",
            telegram_id="-1001",
            username="purmaster",
            title="PUR",
        )

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        return SourceAccessResult(
            status=self.access_status,
            can_read_messages=self.access_status == "succeeded",
            can_read_history=self.access_status == "succeeded",
            resolved_source=source,
            last_message_id=42 if self.access_status == "succeeded" else None,
            error=None if self.access_status == "succeeded" else "operator required",
        )

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        return [_message(source, 41), _message(source, 42)][:limit]

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        after_date: object | None = None,
        limit: int,
    ) -> list[TelegramMessage]:
        return []

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        return MessageContext(message_id, [], [], [])


@pytest.fixture
def source_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "https://t.me/purmaster", purpose="catalog_ingestion", added_by="admin"
        )
        yield session, source


@pytest.mark.asyncio
async def test_access_check_success_writes_check_and_preview_ready(source_session):
    session, source = source_session
    worker = TelegramAccessWorker(session, FakeTelegramClient())

    check = await worker.check_source_access(source.id)

    source_row = session.execute(select(monitored_sources_table)).mappings().one()
    check_row = session.execute(select(source_access_checks_table)).mappings().one()
    assert check.status == "succeeded"
    assert source_row["status"] == "preview_ready"
    assert source_row["telegram_id"] == "-1001"
    assert source_row["title"] == "PUR"
    assert check_row["monitored_source_id"] == source.id
    assert check_row["can_read_messages"] is True
    assert check_row["last_message_id"] == 42


@pytest.mark.asyncio
async def test_access_check_operator_failure_updates_status_and_event(source_session):
    session, source = source_session
    worker = TelegramAccessWorker(session, FakeTelegramClient(access_status="needs_join"))

    check = await worker.check_source_access(source.id)

    source_row = session.execute(select(monitored_sources_table)).mappings().one()
    event_row = session.execute(select(operational_events_table)).mappings().one()
    assert check.status == "needs_join"
    assert source_row["status"] == "needs_join"
    assert event_row["event_type"] == "access_check"
    assert event_row["severity"] == "warning"
    assert event_row["entity_id"] == source.id


@pytest.mark.asyncio
async def test_preview_messages_do_not_move_checkpoint(source_session):
    session, source = source_session
    worker = TelegramAccessWorker(session, FakeTelegramClient())
    check = await worker.check_source_access(source.id)

    await worker.fetch_preview(source.id, access_check_id=check.id, limit=2)

    source_row = session.execute(select(monitored_sources_table)).mappings().one()
    preview_rows = session.execute(select(source_preview_messages_table)).mappings().all()
    assert source_row["checkpoint_message_id"] is None
    assert len(preview_rows) == 2
    assert [row["telegram_message_id"] for row in preview_rows] == [41, 42]


def _message(source: ResolvedTelegramSource, message_id: int) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref=source.input_ref,
        telegram_message_id=message_id,
        message_date=datetime(2026, 4, 28, 12, 0, message_id % 60),
        sender_id="user-1",
        sender_display="User",
        text=f"message {message_id}",
        caption=None,
        has_media=False,
        media_metadata_json=None,
        reply_to_message_id=None,
        thread_id=None,
        forward_metadata_json=None,
        raw_metadata_json={},
    )
