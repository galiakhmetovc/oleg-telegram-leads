from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.enrichments import get_repository, get_task_publisher
from app.domain.enrichment import EnrichmentJobSnapshot, EnrichmentStatus
from app.main import create_app


class ApiInMemoryJobRepository:
    def __init__(self) -> None:
        self.job_id = uuid4()
        self.created_texts: list[str] = []

    async def create_job(self, input_text: str) -> EnrichmentJobSnapshot:
        self.created_texts.append(input_text)
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
        )


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
    assert repository.created_texts == ["Нужна поставка завтра"]
    assert publisher.published == [repository.job_id]
