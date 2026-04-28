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
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.telegram_polling import TelegramPollingWorker


class FakeTelegramClient:
    def __init__(self, messages: list[TelegramMessage]) -> None:
        self.messages = messages
        self.fetch_calls: list[tuple[int | None, int]] = []

    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        return ResolvedTelegramSource(
            input_ref=input_ref,
            source_kind="telegram_supergroup",
            telegram_id="-1001",
            username="example",
            title="Example",
        )

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        return SourceAccessResult(
            status="succeeded",
            can_read_messages=True,
            can_read_history=True,
            resolved_source=source,
        )

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        return self.messages[:limit]

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        limit: int,
    ) -> list[TelegramMessage]:
        self.fetch_calls.append((after_message_id, limit))
        return self.messages[:limit]

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
def polling_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft("@example", purpose="lead_monitoring", added_by="admin")
        service.activate(source.id, actor="admin")
        yield session, source.id


@pytest.mark.asyncio
async def test_poll_active_source_persists_messages_and_checkpoint(polling_session):
    session, source_id = polling_session
    service = TelegramSourceService(session)
    service.reset_checkpoint(source_id, message_id=40, actor="admin", confirm=True)
    job = SchedulerService(session).enqueue(
        job_type="poll_monitored_source",
        scope_type="telegram_source",
        monitored_source_id=source_id,
    )
    client = FakeTelegramClient([_message(41), _message(42)])
    worker = TelegramPollingWorker(session, client)

    result = await worker.poll_monitored_source(source_id, scheduler_job_id=job.id, limit=100)

    source_row = session.execute(select(monitored_sources_table)).mappings().one()
    message_rows = session.execute(select(source_messages_table)).mappings().all()
    job_row = session.execute(select(scheduler_jobs_table)).mappings().one()
    assert result.status == "succeeded"
    assert result.fetched_count == 2
    assert result.inserted_count == 2
    assert client.fetch_calls == [(40, 100)]
    assert source_row["checkpoint_message_id"] == 42
    assert [row["telegram_message_id"] for row in message_rows] == [41, 42]
    assert [row["classification_status"] for row in message_rows] == [
        "unclassified",
        "unclassified",
    ]
    assert message_rows[0]["text"] == "text 41"
    assert message_rows[0]["caption"] == "caption 41"
    assert message_rows[0]["sender_id"] == "sender-1"
    assert message_rows[0]["reply_to_message_id"] == 40
    assert message_rows[0]["thread_id"] == "thread-1"
    assert message_rows[0]["forward_metadata_json"] == {"from": "source"}
    assert job_row["checkpoint_before_json"] == {"message_id": 40}
    assert job_row["checkpoint_after_json"] == {"message_id": 42}
    assert job_row["result_summary_json"] == {
        "status": "succeeded",
        "fetched_count": 2,
        "inserted_count": 2,
        "duplicate_count": 0,
    }


@pytest.mark.asyncio
async def test_poll_deduplicates_by_source_and_message_id(polling_session):
    session, source_id = polling_session
    client = FakeTelegramClient([_message(41), _message(41), _message(42)])
    worker = TelegramPollingWorker(session, client)

    first = await worker.poll_monitored_source(source_id, limit=100)
    second = await worker.poll_monitored_source(source_id, limit=100)

    message_rows = session.execute(select(source_messages_table)).mappings().all()
    assert first.inserted_count == 2
    assert second.inserted_count == 0
    assert second.duplicate_count == 3
    assert [row["telegram_message_id"] for row in message_rows] == [41, 42]


@pytest.mark.asyncio
async def test_poll_skips_non_active_sources(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        source = TelegramSourceService(session).create_draft(
            "@example",
            purpose="lead_monitoring",
            added_by="admin",
        )
        client = FakeTelegramClient([_message(41)])
        worker = TelegramPollingWorker(session, client)

        result = await worker.poll_monitored_source(source.id, limit=100)

        assert result.status == "skipped"
        assert result.reason == "source_not_active"
        assert client.fetch_calls == []
        assert session.execute(select(source_messages_table)).mappings().all() == []


def _message(message_id: int) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="@example",
        telegram_message_id=message_id,
        message_date=datetime(2026, 4, 28, 12, 0, message_id % 60),
        sender_id="sender-1",
        sender_display="Sender One",
        text=f"text {message_id}",
        caption=f"caption {message_id}",
        has_media=True,
        media_metadata_json={"kind": "photo"},
        reply_to_message_id=message_id - 1,
        thread_id="thread-1",
        forward_metadata_json={"from": "source"},
        raw_metadata_json={"raw": message_id},
    )
