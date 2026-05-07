from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.analytics import get_analytics_repository
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidatePage
from app.domain.analytics import AnalyticsRun
from app.main import create_app


class ApiInMemoryAnalyticsRepository:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.runs = [
            AnalyticsRun(
                id=self.run_id,
                name="designer-channel",
                source="batch",
                input_path="artifacts/designer-channel/messages.jsonl",
                run_dir="artifacts/designer-channel/runs/2026-05-07-full-8workers",
                processed=528953,
                skipped=0,
                failed=0,
                leads=16001,
                started_at=datetime(2026, 5, 7, 17, 34, tzinfo=UTC),
                finished_at=datetime(2026, 5, 7, 19, 15, tzinfo=UTC),
                imported_at=datetime(2026, 5, 7, 19, 20, tzinfo=UTC),
                summary={"workers": 8},
            )
        ]
        self.aggregates = [
            AnalyticsAggregate(
                kind="score_bucket",
                key="35-59",
                label="35-59",
                count=9000,
                payload={"min_score": 35, "max_score": 59},
            ),
            AnalyticsAggregate(
                kind="signal",
                key="need",
                label="Потребность",
                count=3200,
                payload={"examples": ["нужно"]},
            ),
        ]
        self.candidates = [
            AnalyticsCandidate(
                run_id=self.run_id,
                message_id="488906",
                text="Подскажите на счет умного дома Яндекс",
                score=247,
                temperature="hot",
                solution_areas=[
                    {
                        "type": "smart_home",
                        "label": "Умный дом / автоматизация",
                        "matched_types": ["smart_home_automation"],
                    }
                ],
                customer_segments=[],
                intent_signals=[],
                noise_signals=[],
                reasons=[
                    {
                        "source": "domain_signal",
                        "key": "smart_home_automation",
                        "label": "Умный дом / автоматизация",
                        "weight": 35,
                        "matched_texts": ["умный дом"],
                    }
                ],
                domain_signals=[],
                facts=[],
            )
        ]

    async def list_runs(self) -> list[AnalyticsRun]:
        return self.runs

    async def get_run(self, run_id: UUID) -> AnalyticsRun | None:
        return self.runs[0] if run_id == self.run_id else None

    async def list_aggregates(self, run_id: UUID) -> list[AnalyticsAggregate]:
        if run_id != self.run_id:
            return []
        return self.aggregates

    async def list_candidates(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
        score_min: int | None,
        temperature: str | None,
        signal: str | None,
        q: str | None,
    ) -> AnalyticsCandidatePage:
        items = self.candidates
        if score_min is not None:
            items = [item for item in items if item.score >= score_min]
        if temperature is not None:
            items = [item for item in items if item.temperature == temperature]
        return AnalyticsCandidatePage(total=len(items), items=items[offset : offset + limit])


def test_lists_analytics_runs() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get("/api/v1/analytics/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runs"][0]["id"] == str(repository.run_id)
    assert payload["runs"][0]["processed"] == 528953
    assert payload["runs"][0]["leads"] == 16001
    assert payload["runs"][0]["candidate_rate"] == 3.025032


def test_returns_analytics_summary_with_grouped_aggregates() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(f"/api/v1/analytics/runs/{repository.run_id}/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["id"] == str(repository.run_id)
    assert payload["aggregates"]["score_bucket"][0]["key"] == "35-59"
    assert payload["aggregates"]["signal"][0]["count"] == 3200


def test_lists_analytics_candidates_with_filters() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"score_min": 90, "temperature": "hot", "limit": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["message_id"] == "488906"
    assert payload["items"][0]["score"] == 247
    assert payload["items"][0]["reasons"][0]["matched_texts"] == ["умный дом"]
