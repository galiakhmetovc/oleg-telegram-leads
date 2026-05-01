from datetime import datetime, timedelta
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from sqlalchemy import select

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramMediaDownload,
    TelegramMessage,
)
from pur_leads.models.catalog import parsed_chunks_table, sources_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import (
    monitored_sources_table,
    source_messages_table,
    telegram_raw_export_runs_table,
)
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.telegram_sources import TelegramSourceService
from pur_leads.workers.telegram_polling import TelegramPollingWorker


class FakeTelegramClient:
    def __init__(self, messages: list[TelegramMessage]) -> None:
        self.messages = messages
        self.fetch_calls: list[dict] = []
        self.iter_calls: list[dict] = []
        self.download_calls: list[dict] = []

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
        after_date: datetime | None = None,
        limit: int,
    ) -> list[TelegramMessage]:
        self.fetch_calls.append(
            {"after_message_id": after_message_id, "after_date": after_date, "limit": limit}
        )
        return self.messages[:limit]

    async def iter_message_batches(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None = None,
        from_message_id: int | None = None,
        after_date: datetime | None = None,
        limit: int | None = None,
        batch_size: int = 1000,
    ):
        self.iter_calls.append(
            {
                "after_message_id": after_message_id,
                "from_message_id": from_message_id,
                "after_date": after_date,
                "limit": limit,
                "batch_size": batch_size,
            }
        )
        rows = self.messages[:limit] if limit is not None else self.messages
        for index in range(0, len(rows), batch_size):
            yield rows[index : index + batch_size]

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

    async def download_message_media(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
        allowed_media_types: list[str],
        max_file_size_bytes: int | None,
    ) -> TelegramMediaDownload:
        self.download_calls.append(
            {
                "message_id": message_id,
                "destination_dir": str(destination_dir),
                "allowed_media_types": list(allowed_media_types),
                "max_file_size_bytes": max_file_size_bytes,
            }
        )
        message = next(row for row in self.messages if row.telegram_message_id == message_id)
        document = (message.media_metadata_json or {}).get("document", {})
        file_size = document.get("file_size")
        file_name = document.get("file_name")
        mime_type = document.get("mime_type")
        if max_file_size_bytes is not None and file_size and file_size > max_file_size_bytes:
            return TelegramMediaDownload(
                status="skipped",
                media_type="document",
                file_name=file_name,
                mime_type=mime_type,
                file_size=file_size,
                local_path=None,
                skip_reason="file_too_large",
            )
        destination = Path(destination_dir) / str(file_name or f"{message_id}.bin")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"document")
        return TelegramMediaDownload(
            status="downloaded",
            media_type="document",
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            local_path=str(destination),
        )


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
    job_row = (
        session.execute(select(scheduler_jobs_table).where(scheduler_jobs_table.c.id == job.id))
        .mappings()
        .one()
    )
    assert result.status == "succeeded"
    assert result.fetched_count == 2
    assert result.inserted_count == 2
    assert client.fetch_calls == [{"after_message_id": 40, "after_date": None, "limit": 100}]
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
async def test_poll_source_writes_raw_json_parquet_before_canonical(polling_session, tmp_path):
    session, source_id = polling_session
    service = TelegramSourceService(session)
    service.reset_checkpoint(source_id, message_id=40, actor="admin", confirm=True)
    client = FakeTelegramClient([_message(41)])
    worker = TelegramPollingWorker(session, client, raw_export_root=tmp_path / "raw")

    result = await worker.poll_monitored_source(source_id, limit=100)

    assert result.inserted_count == 1
    run = session.execute(select(telegram_raw_export_runs_table)).mappings().one()
    message = session.execute(select(source_messages_table)).mappings().one()
    assert run["status"] == "succeeded"
    assert run["message_count"] == 1
    assert message["archive_pointer_id"] == run["id"]
    assert message["raw_metadata_json"]["raw_export"]["run_id"] == run["id"]

    result_json = json.loads(Path(run["result_json_path"]).read_text(encoding="utf-8"))
    assert result_json["messages"][0]["id"] == 41
    assert result_json["messages"][0]["raw_telethon_json"] == {"raw": 41}

    parquet_rows = pq.read_table(run["messages_parquet_path"]).to_pylist()
    assert parquet_rows[0]["telegram_message_id"] == 41
    assert json.loads(parquet_rows[0]["raw_message_json"]) == result_json["messages"][0]

    extract_jobs = session.execute(
        select(scheduler_jobs_table).where(
            scheduler_jobs_table.c.job_type == "extract_catalog_facts"
        )
    ).all()
    assert extract_jobs == []


@pytest.mark.asyncio
async def test_configured_raw_export_reuses_one_telegram_fetch_and_does_not_start_ai(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
            start_mode="from_beginning",
        )
        service.reset_checkpoint(source.id, message_id=40, actor="admin", confirm=True)
        job = SchedulerService(session).enqueue(
            job_type="export_telegram_raw",
            scope_type="telegram_source",
            monitored_source_id=source.id,
            payload_json={
                "range": {"mode": "since_checkpoint", "batch_size": 2, "max_messages": 3},
                "media": {
                    "enabled": True,
                    "types": ["document"],
                    "max_file_size_bytes": 10,
                },
                "canonicalize": True,
                "enqueue_classification": False,
            },
        )
        client = FakeTelegramClient(
            [
                _message_with_values(
                    41,
                    text="catalog text",
                    caption="catalog.pdf",
                    media_metadata={
                        "type": "MessageMediaDocument",
                        "document": {
                            "file_name": "catalog.pdf",
                            "mime_type": "application/pdf",
                            "file_size": 7,
                            "downloadable": True,
                        },
                    },
                ),
                _message_with_values(42, text="plain", caption=None, media_metadata=None),
                _message_with_values(
                    43,
                    text="large document",
                    caption="large.pdf",
                    media_metadata={
                        "type": "MessageMediaDocument",
                        "document": {
                            "file_name": "large.pdf",
                            "mime_type": "application/pdf",
                            "file_size": 99,
                            "downloadable": True,
                        },
                    },
                ),
            ]
        )
        worker = TelegramPollingWorker(session, client, raw_export_root=tmp_path / "raw")

        result = await worker.export_monitored_source_raw(
            source.id,
            scheduler_job_id=job.id,
            range_config=job.payload_json["range"],
            media_config=job.payload_json["media"],
            canonicalize=True,
        )

        assert result.status == "succeeded"
        assert result.fetched_count == 3
        assert result.inserted_count == 3
        assert client.iter_calls == [
            {
                "after_message_id": 40,
                "from_message_id": None,
                "after_date": None,
                "limit": 3,
                "batch_size": 2,
            }
        ]
        assert [call["message_id"] for call in client.download_calls] == [41, 43]
        run = session.execute(select(telegram_raw_export_runs_table)).mappings().one()
        assert run["status"] == "succeeded"
        assert run["message_count"] == 3
        assert run["metadata_json"]["range"]["mode"] == "since_checkpoint"
        assert run["metadata_json"]["media"]["types"] == ["document"]
        message_rows = (
            session.execute(
                select(source_messages_table).order_by(source_messages_table.c.telegram_message_id)
            )
            .mappings()
            .all()
        )
        assert [row["telegram_message_id"] for row in message_rows] == [41, 42, 43]
        assert {row["archive_pointer_id"] for row in message_rows} == {run["id"]}
        assert message_rows[0]["media_metadata_json"]["raw_export_download"]["status"] == (
            "downloaded"
        )
        assert message_rows[2]["media_metadata_json"]["raw_export_download"]["skip_reason"] == (
            "file_too_large"
        )
        result_json = json.loads(Path(run["result_json_path"]).read_text(encoding="utf-8"))
        assert (
            result_json["messages"][0]["raw_media_json"]["raw_export_download"]["status"]
            == "downloaded"
        )
        parquet_rows = pq.read_table(run["messages_parquet_path"]).to_pylist()
        assert [row["telegram_message_id"] for row in parquet_rows] == [41, 42, 43]
        extract_jobs = session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "extract_catalog_facts"
            )
        ).all()
        assert extract_jobs == []


@pytest.mark.asyncio
async def test_poll_lead_source_enqueues_classification_and_moves_next_poll(
    polling_session,
):
    session, source_id = polling_session
    service = TelegramSourceService(session)
    service.reset_checkpoint(source_id, message_id=40, actor="admin", confirm=True)
    job = SchedulerService(session).enqueue(
        job_type="poll_monitored_source",
        scope_type="telegram_source",
        monitored_source_id=source_id,
    )
    client = FakeTelegramClient([_message(41)])
    worker = TelegramPollingWorker(session, client)

    result = await worker.poll_monitored_source(source_id, scheduler_job_id=job.id, limit=100)

    source_row = session.execute(select(monitored_sources_table)).mappings().one()
    jobs = (
        session.execute(select(scheduler_jobs_table).order_by(scheduler_jobs_table.c.created_at))
        .mappings()
        .all()
    )
    classify_jobs = [row for row in jobs if row["job_type"] == "classify_message_batch"]
    assert result.inserted_count == 1
    assert source_row["next_poll_at"] is not None
    assert source_row["next_poll_at"] > source_row["last_success_at"]
    assert len(classify_jobs) == 1
    assert classify_jobs[0]["status"] == "queued"
    assert classify_jobs[0]["monitored_source_id"] == source_id
    assert classify_jobs[0]["idempotency_key"] == f"source:{source_id}:classify:active"
    assert classify_jobs[0]["payload_json"] == {
        "limit": 100,
        "trigger": "poll_monitored_source",
    }


@pytest.mark.asyncio
async def test_poll_recent_days_source_fetches_from_start_date_until_checkpoint_exists(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "@example",
            purpose="lead_monitoring",
            added_by="admin",
            start_recent_days=183,
        )
        service.activate(source.id, actor="admin")
        client = FakeTelegramClient([_message(41)])
        worker = TelegramPollingWorker(session, client)

        result = await worker.poll_monitored_source(source.id, limit=100)

        assert result.inserted_count == 1
        assert client.fetch_calls[0]["after_message_id"] is None
        assert client.fetch_calls[0]["after_date"] is not None
        assert client.fetch_calls[0]["after_date"].date() == (
            datetime.now(tz=client.fetch_calls[0]["after_date"].tzinfo).date() - timedelta(days=183)
        )


@pytest.mark.asyncio
async def test_poll_catalog_source_creates_raw_source_chunks_and_document_job(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
        )
        service.activate(source.id, actor="admin")
        service.reset_checkpoint(source.id, message_id=40, actor="admin", confirm=True)
        job = SchedulerService(session).enqueue(
            job_type="poll_monitored_source",
            scope_type="telegram_source",
            monitored_source_id=source.id,
        )
        client = FakeTelegramClient(
            [
                _message_with_values(
                    41,
                    text="Dahua Hero A1 camera",
                    caption="PDF catalog",
                    media_metadata={
                        "type": "MessageMediaDocument",
                        "document": {
                            "file_name": "catalog.pdf",
                            "mime_type": "application/pdf",
                            "file_size": 1234,
                            "downloadable": True,
                        },
                    },
                )
            ]
        )
        worker = TelegramPollingWorker(session, client)

        result = await worker.poll_monitored_source(source.id, scheduler_job_id=job.id, limit=100)

        message_row = session.execute(select(source_messages_table)).mappings().one()
        raw_source = session.execute(select(sources_table)).mappings().one()
        chunk = session.execute(select(parsed_chunks_table)).mappings().one()
        jobs = (
            session.execute(
                select(scheduler_jobs_table).order_by(scheduler_jobs_table.c.created_at)
            )
            .mappings()
            .all()
        )
        document_job = [row for row in jobs if row["job_type"] == "download_artifact"][0]
        assert result.inserted_count == 1
        assert message_row["raw_source_id"] == raw_source["id"]
        assert raw_source["source_type"] == "telegram_message"
        assert raw_source["origin"] == "telegram:purmaster"
        assert raw_source["external_id"] == "41"
        assert raw_source["raw_text"] == "Dahua Hero A1 camera\nPDF catalog"
        assert chunk["source_id"] == raw_source["id"]
        assert chunk["text"] == "Dahua Hero A1 camera\nPDF catalog"
        assert document_job["source_message_id"] == message_row["id"]
        assert document_job["monitored_source_id"] == source.id
        assert document_job["priority"] == "high"
        assert document_job["payload_json"]["source_id"] == raw_source["id"]
        assert document_job["payload_json"]["telegram_message_id"] == 41


@pytest.mark.asyncio
async def test_poll_catalog_source_enqueues_allowed_external_page_job(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
        )
        service.activate(source.id, actor="admin")
        service.reset_checkpoint(source.id, message_id=40, actor="admin", confirm=True)
        client = FakeTelegramClient(
            [
                _message_with_values(
                    41,
                    text=(
                        "Подробности: "
                        "https://telegra.ph/PUR-Umnyj-Dom-glazami-inzhenera-01-31 "
                        "и неразрешенная https://example.com/vendor"
                    ),
                    caption=None,
                    media_metadata=None,
                )
            ]
        )
        worker = TelegramPollingWorker(session, client)

        result = await worker.poll_monitored_source(source.id, limit=100)

        message_row = session.execute(select(source_messages_table)).mappings().one()
        raw_source = session.execute(select(sources_table)).mappings().one()
        external_jobs = (
            session.execute(
                select(scheduler_jobs_table).where(
                    scheduler_jobs_table.c.job_type == "fetch_external_page"
                )
            )
            .mappings()
            .all()
        )
        assert result.inserted_count == 1
        assert len(external_jobs) == 1
        assert external_jobs[0]["source_message_id"] == message_row["id"]
        assert external_jobs[0]["monitored_source_id"] == source.id
        assert external_jobs[0]["payload_json"] == {
            "url": "https://telegra.ph/PUR-Umnyj-Dom-glazami-inzhenera-01-31",
            "parent_source_id": raw_source["id"],
            "source_message_id": message_row["id"],
            "monitored_source_id": source.id,
        }


@pytest.mark.asyncio
async def test_poll_catalog_source_does_not_auto_extract_message_text(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = TelegramSourceService(session)
        source = service.create_draft(
            "https://t.me/purmaster",
            purpose="catalog_ingestion",
            added_by="admin",
        )
        service.activate(source.id, actor="admin")
        service.reset_checkpoint(source.id, message_id=40, actor="admin", confirm=True)
        client = FakeTelegramClient(
            [
                _message_with_values(
                    41,
                    text="Dahua Hero A1 камера для дома",
                    caption=None,
                    media_metadata=None,
                )
            ]
        )
        worker = TelegramPollingWorker(session, client)

        result = await worker.poll_monitored_source(source.id, limit=100)

        chunk = session.execute(select(parsed_chunks_table)).mappings().one()
        extract_jobs = session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "extract_catalog_facts"
            )
        ).all()
        assert result.inserted_count == 1
        assert chunk["text"] == "Dahua Hero A1 камера для дома"
        assert extract_jobs == []


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
    return _message_with_values(
        message_id,
        text=f"text {message_id}",
        caption=f"caption {message_id}",
        media_metadata={"kind": "photo"},
    )


def _message_with_values(
    message_id: int,
    *,
    text: str,
    caption: str | None,
    media_metadata: dict | None,
) -> TelegramMessage:
    return TelegramMessage(
        monitored_source_ref="@example",
        telegram_message_id=message_id,
        message_date=datetime(2026, 4, 28, 12, 0, message_id % 60),
        sender_id="sender-1",
        sender_display="Sender One",
        text=text,
        caption=caption,
        has_media=media_metadata is not None,
        media_metadata_json=media_metadata,
        reply_to_message_id=message_id - 1,
        thread_id="thread-1",
        forward_metadata_json={"from": "source"},
        raw_metadata_json={"raw": message_id},
    )
