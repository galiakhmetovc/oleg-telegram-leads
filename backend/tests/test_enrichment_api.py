from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.enrichments import get_repository, get_task_publisher
from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentStatus, EnrichmentTaskOutboxItem
from app.main import create_app


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
            created_at=datetime(2026, 5, 7, tzinfo=UTC),
            started_at=None,
            finished_at=None,
            nlp_config_revision_id=UUID("00000000-0000-0000-0000-000000000123"),
            nlp_config_revision=12,
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
                claimed_at=datetime(2026, 5, 7, tzinfo=UTC),
                created_at=datetime(2026, 5, 7, tzinfo=UTC),
                updated_at=datetime(2026, 5, 7, tzinfo=UTC),
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


def test_create_enrichment_endpoint_returns_job_snapshot_and_publishes_task() -> None:
    repository = ApiInMemoryJobRepository()
    publisher = ApiRecordingTaskPublisher()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_task_publisher] = lambda: publisher
    client = TestClient(app)

    response = client.post("/api/v1/enrichments", json={"text": "Нужна поставка завтра"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(repository.job_id)
    assert payload["status"] == "queued"
    assert payload["progress_percent"] == 0
    assert payload["nlp_config_revision_id"] == "00000000-0000-0000-0000-000000000123"
    assert payload["nlp_config_revision"] == 12
    assert repository.created_texts == ["Нужна поставка завтра"]
    assert publisher.published == [repository.job_id]
    assert repository.outbox_status == "published"
