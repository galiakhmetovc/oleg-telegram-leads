from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.enrichments import get_task_publisher
from app.api.golden_examples import get_enrichment_repository, get_golden_examples_repository
from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentStatus, EnrichmentTaskOutboxItem
from app.domain.golden_examples import GoldenExample
from app.main import create_app


class ApiInMemoryGoldenExamplesRepository:
    def __init__(self) -> None:
        self.examples: dict[UUID, GoldenExample] = {}
        self.source_index: dict[UUID, UUID] = {}
        self.source_messages: dict[UUID, dict[str, object]] = {}

    async def list_examples(self, *, limit: int, offset: int) -> tuple[int, list[GoldenExample]]:
        items = sorted(self.examples.values(), key=lambda item: item.created_at, reverse=True)
        return len(items), items[offset : offset + limit]

    async def create_example(
        self,
        *,
        text: str,
        title: str | None,
        expected_verdict: str | None,
        comment: str,
    ) -> GoldenExample:
        example = _golden_example(
            text=text,
            title=title or "Golden example",
            expected_verdict=expected_verdict,
            comment=comment,
        )
        self.examples[example.id] = example
        return example

    async def get_by_source_message_id(self, source_message_id: UUID) -> GoldenExample | None:
        example_id = self.source_index.get(source_message_id)
        return self.examples.get(example_id) if example_id is not None else None

    async def create_from_source_message(self, source_message_id: UUID) -> GoldenExample | None:
        source = self.source_messages.get(source_message_id)
        if source is None:
            return None
        example = _golden_example(
            text=str(source["text"]),
            title=str(source["title"]),
            expected_verdict=source.get("expected_verdict"),
            comment=str(source.get("comment") or ""),
            source_message_id=source_message_id,
            source_chat_title=str(source.get("source_chat_title") or ""),
            telegram_message_id=int(cast(Any, source["telegram_message_id"])),
        )
        self.examples[example.id] = example
        self.source_index[source_message_id] = example.id
        return example

    async def get_example(self, example_id: UUID) -> GoldenExample | None:
        return self.examples.get(example_id)

    async def set_last_enrichment_job(self, *, example_id: UUID, job_id: UUID) -> GoldenExample | None:
        example = self.examples.get(example_id)
        if example is None:
            return None
        updated = GoldenExample(
            id=example.id,
            title=example.title,
            text=example.text,
            expected_verdict=example.expected_verdict,
            comment=example.comment,
            source_message_id=example.source_message_id,
            source_chat_title=example.source_chat_title,
            telegram_message_id=example.telegram_message_id,
            telegram_message_url=example.telegram_message_url,
            last_enrichment_job_id=job_id,
            created_at=example.created_at,
            updated_at=datetime(2026, 5, 9, 12, 5, tzinfo=UTC),
        )
        self.examples[example_id] = updated
        return updated


class ApiInMemoryJobRepository:
    def __init__(self) -> None:
        self.job_id = uuid4()
        self.created_texts: list[str] = []
        self.outbox_status: str | None = None

    async def create_job(self, input_text: str, *, publish_ready: bool = False) -> EnrichmentJobSnapshot:
        self.created_texts.append(input_text)
        self.outbox_status = "pending" if publish_ready else "blocked"
        return EnrichmentJobSnapshot(
            id=self.job_id,
            input_text=input_text,
            status=EnrichmentStatus.QUEUED,
            progress_percent=0,
            current_stage=None,
            stage_index=0,
            stage_count=0,
            stage_progress_percent=0,
            message="Задача поставлена в очередь",
            result=None,
            error=None,
            created_at=datetime(2026, 5, 9, tzinfo=UTC),
            started_at=None,
            finished_at=None,
        )

    async def mark_task_pending(self, job_id: UUID) -> None:
        self.outbox_status = "pending"

    async def claim_pending_tasks(self, *, limit: int, job_id: UUID | None = None) -> list[EnrichmentTaskOutboxItem]:
        assert job_id == self.job_id
        assert self.outbox_status == "pending"
        self.outbox_status = "sending"
        return [
            EnrichmentTaskOutboxItem(
                job_id=self.job_id,
                task_name="app.worker.tasks.enrich_text_job",
                status="sending",
                attempts=1,
                last_error=None,
                claimed_at=datetime(2026, 5, 9, tzinfo=UTC),
                created_at=datetime(2026, 5, 9, tzinfo=UTC),
                updated_at=datetime(2026, 5, 9, tzinfo=UTC),
                published_at=None,
            )
        ]

    async def mark_tasks_published(self, job_ids: list[UUID]) -> None:
        assert job_ids == [self.job_id]
        self.outbox_status = "published"

    async def release_tasks(self, job_ids: list[UUID], *, error: str) -> None:
        assert job_ids == [self.job_id]
        self.outbox_status = "pending"


class ApiRecordingTaskPublisher:
    def __init__(self) -> None:
        self.published: list[UUID] = []

    async def publish(self, job_id: UUID) -> None:
        self.published.append(job_id)


def test_creates_lists_and_runs_golden_examples() -> None:
    golden_repository = ApiInMemoryGoldenExamplesRepository()
    enrichment_repository = ApiInMemoryJobRepository()
    publisher = ApiRecordingTaskPublisher()
    app = create_app()
    app.dependency_overrides[get_golden_examples_repository] = lambda: golden_repository
    app.dependency_overrides[get_enrichment_repository] = lambda: enrichment_repository
    app.dependency_overrides[get_task_publisher] = lambda: publisher
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/golden-examples",
        json={
            "text": "Нужен подрядчик на умный дом",
            "title": "Умный дом",
            "expected_verdict": "lead",
            "comment": "Базовый горячий лид",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["text"] == "Нужен подрядчик на умный дом"
    assert created["expected_verdict"] == "lead"

    list_response = client.get("/api/v1/golden-examples")

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == created["id"]

    run_response = client.post(f"/api/v1/golden-examples/{created['id']}/run")

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["example"]["last_enrichment_job_id"] == str(enrichment_repository.job_id)
    assert run_payload["job"]["id"] == str(enrichment_repository.job_id)
    assert enrichment_repository.created_texts == ["Нужен подрядчик на умный дом"]
    assert publisher.published == [enrichment_repository.job_id]
    assert enrichment_repository.outbox_status == "published"


def test_creates_golden_example_from_source_message_idempotently() -> None:
    source_message_id = uuid4()
    golden_repository = ApiInMemoryGoldenExamplesRepository()
    golden_repository.source_messages[source_message_id] = {
        "text": "Подскажите контакты по видеонаблюдению",
        "title": "Чат дизайнеров #479044",
        "expected_verdict": "lead",
        "comment": "Подтверждено ревью",
        "source_chat_title": "Чат дизайнеров",
        "telegram_message_id": 479044,
    }
    app = create_app()
    app.dependency_overrides[get_golden_examples_repository] = lambda: golden_repository
    client = TestClient(app)

    first_response = client.post(f"/api/v1/golden-examples/from-message/{source_message_id}")
    second_response = client.post(f"/api/v1/golden-examples/from-message/{source_message_id}")

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert first_response.json()["id"] == second_response.json()["id"]
    assert first_response.json()["source_message_id"] == str(source_message_id)
    assert first_response.json()["source_chat_title"] == "Чат дизайнеров"


def _golden_example(
    *,
    text: str,
    title: str,
    expected_verdict: object | None,
    comment: str,
    source_message_id: UUID | None = None,
    source_chat_title: str | None = None,
    telegram_message_id: int | None = None,
) -> GoldenExample:
    return GoldenExample(
        id=uuid4(),
        title=title,
        text=text,
        expected_verdict=cast(Any, str(expected_verdict) if expected_verdict is not None else None),
        comment=comment,
        source_message_id=source_message_id,
        source_chat_title=source_chat_title,
        telegram_message_id=telegram_message_id,
        telegram_message_url=None,
        last_enrichment_job_id=None,
        created_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
    )
