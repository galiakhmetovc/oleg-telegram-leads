from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.analytics import get_analytics_repository
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidatePage
from app.domain.analytics import AnalyticsMessageReview, AnalyticsRun
from app.domain.analytics import AnalyticsReviewVerdict
from app.application.evaluation.review_eval import ReviewEvalRow
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
            AnalyticsAggregate(
                kind="review_lane",
                key="direct_pur_lead",
                label="Прямой лид ПУР",
                count=1,
                payload={"description": "Высокий приоритет для ручной проверки"},
            ),
        ]
        self.candidates = [
            AnalyticsCandidate(
                run_id=self.run_id,
                message_id="488906",
                text="Подскажите на счет умного дома Яндекс",
                score=247,
                temperature="hot",
                review_lane="direct_pur_lead",
                solution_areas=[
                    {
                        "type": "smart_home",
                        "label": "Умный дом / автоматизация",
                        "matched_types": ["smart_home_automation"],
                    }
                ],
                customer_segments=[
                    {
                        "type": "designers",
                        "label": "Дизайнеры",
                        "matched_types": ["designer_context"],
                    }
                ],
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
                is_lead=True,
                received_at=datetime(2026, 5, 8, 12, 30, tzinfo=UTC),
                source_chat_id="designers",
                source_chat_title="Чат дизайнеров",
            )
        ]
        self.reviews: dict[str, AnalyticsMessageReview] = {}
        self.cancelled_notifications: list[tuple[str, str]] = []
        self.review_eval_rows = [
            ReviewEvalRow(
                source_message_id="fp",
                telegram_message_id=479071,
                source_chat_title="Dahua Support",
                verdict="noise",
                predicted_is_lead=True,
                score=105,
                temperature="hot",
                review_lane="domain_interest",
                text="Добро пожаловать в чат Dahua Support. Бот создан в @botsbaseru",
            ),
            ReviewEvalRow(
                source_message_id="fn",
                telegram_message_id=479072,
                source_chat_title="Designers",
                verdict="lead",
                predicted_is_lead=False,
                score=10,
                temperature="cold",
                review_lane="other_candidate",
                text="Нужен подрядчик на видеонаблюдение",
            ),
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
        reason: str | None = None,
        solution_area: str | None = None,
        customer_segment: str | None = None,
        lane: str | None = None,
        q: str | None,
        source_chat_id: str | None = None,
        received_from: datetime | None = None,
        received_to: datetime | None = None,
        review_status: str | None = None,
        verdict: AnalyticsReviewVerdict | None = None,
    ) -> AnalyticsCandidatePage:
        items = self.candidates
        if score_min is not None:
            items = [item for item in items if item.score >= score_min]
        if temperature is not None:
            items = [item for item in items if item.temperature == temperature]
        if reason is not None:
            items = [item for item in items if any(item_reason["key"] == reason for item_reason in item.reasons)]
        if solution_area is not None:
            items = [item for item in items if any(area["type"] == solution_area for area in item.solution_areas)]
        if customer_segment is not None:
            items = [item for item in items if any(segment["type"] == customer_segment for segment in item.customer_segments)]
        if lane is not None:
            items = [item for item in items if item.review_lane == lane]
        if source_chat_id is not None:
            items = [item for item in items if item.source_chat_id == source_chat_id]
        if received_from is not None:
            items = [item for item in items if item.received_at and item.received_at >= received_from]
        if received_to is not None:
            items = [item for item in items if item.received_at and item.received_at <= received_to]
        if review_status == "reviewed":
            items = [item for item in items if item.review is not None]
        if review_status == "unreviewed":
            items = [item for item in items if item.review is None]
        if verdict is not None:
            items = [item for item in items if item.review is not None and item.review.verdict == verdict]
        return AnalyticsCandidatePage(total=len(items), items=items[offset : offset + limit])

    async def get_live_candidate_by_message_id(self, message_id: str) -> AnalyticsCandidate | None:
        return next((candidate for candidate in self.candidates if candidate.message_id == message_id), None)

    async def get_message_review(self, message_id: str) -> AnalyticsMessageReview | None:
        return self.reviews.get(message_id)

    async def save_message_review(
        self,
        *,
        message_id: str,
        verdict: AnalyticsReviewVerdict | None,
        comment: str,
        tags: list[str] | None = None,
    ) -> AnalyticsMessageReview:
        review = AnalyticsMessageReview(
            source_message_id=message_id,
            verdict=verdict,
            comment=comment,
            tags=tags or [],
            created_at=datetime(2026, 5, 8, 13, 0, tzinfo=UTC),
            updated_at=datetime(2026, 5, 8, 13, 5, tzinfo=UTC),
        )
        self.reviews[message_id] = review
        return review

    async def cancel_unsent_notifications_for_message(self, message_id: str, *, reason: str) -> int:
        self.cancelled_notifications.append((message_id, reason))
        return 1

    async def list_review_eval_rows(self, *, limit: int | None = None) -> list[ReviewEvalRow]:
        if limit is None:
            return self.review_eval_rows
        return self.review_eval_rows[:limit]


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
    assert payload["aggregates"]["review_lane"][0]["key"] == "direct_pur_lead"


def test_returns_review_eval_report() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get("/api/v1/analytics/review-eval")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reviewed"] == 2
    assert payload["evaluated"] == 2
    assert payload["false_positive"] == 1
    assert payload["false_negative"] == 1
    assert payload["precision"] == 0.0
    assert payload["recall"] == 0.0
    assert payload["by_verdict"] == {"noise": 1, "lead": 1}
    assert payload["false_positives"][0]["source_message_id"] == "fp"
    assert payload["false_negatives"][0]["source_message_id"] == "fn"


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
    assert payload["items"][0]["review_lane"] == "direct_pur_lead"
    assert payload["items"][0]["reasons"][0]["matched_texts"] == ["умный дом"]
    assert payload["items"][0]["received_at"] == "2026-05-08T12:30:00Z"
    assert payload["items"][0]["source_chat_id"] == "designers"
    assert payload["items"][0]["source_chat_title"] == "Чат дизайнеров"


def test_filters_analytics_candidates_by_source_channel_and_received_period() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488910",
            text="Другой канал",
            score=150,
            temperature="hot",
            review_lane="direct_pur_lead",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            domain_signals=[],
            facts=[],
            received_at=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
            source_chat_id="other",
            source_chat_title="Другой канал",
        )
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={
            "source_chat_id": "designers",
            "received_from": "2026-05-08T00:00:00Z",
            "received_to": "2026-05-08T23:59:59Z",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["message_id"] == "488906"


def test_filters_analytics_candidates_by_reason_key() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488907",
            text="Нерелевантная причина",
            score=90,
            temperature="hot",
            review_lane="domain_interest",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[
                {
                    "source": "domain_signal",
                    "key": "video_surveillance",
                    "label": "Видеонаблюдение",
                    "weight": 35,
                    "matched_texts": ["камера"],
                }
            ],
            domain_signals=[],
            facts=[],
        )
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"reason": "smart_home_automation"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["message_id"] == "488906"


def test_filters_analytics_candidates_by_segments() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488908",
            text="Другой сегмент",
            score=110,
            temperature="hot",
            review_lane="domain_interest",
            solution_areas=[
                {
                    "type": "security",
                    "label": "Безопасность",
                    "matched_types": ["video_surveillance"],
                }
            ],
            customer_segments=[
                {
                    "type": "homeowners",
                    "label": "Владельцы домов",
                    "matched_types": ["private_house"],
                }
            ],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            domain_signals=[],
            facts=[],
        )
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"solution_area": "smart_home", "customer_segment": "designers"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["message_id"] == "488906"


def test_filters_analytics_candidates_by_review_lane() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488909",
            text="Похоже на доменный интерес, но не прямой лид",
            score=70,
            temperature="warm",
            review_lane="domain_interest",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            domain_signals=[],
            facts=[],
        )
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"lane": "direct_pur_lead"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["message_id"] == "488906"


def test_lists_analytics_candidates_with_review_status_and_verdict_filters() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates[0] = AnalyticsCandidate(
        **{
            **repository.candidates[0].__dict__,
            "review": AnalyticsMessageReview(
                source_message_id="488906",
                verdict="not_lead",
                comment="Нет запроса на подрядчика",
                tags=["no_provider_intent"],
                created_at=datetime(2026, 5, 8, 13, 0, tzinfo=UTC),
                updated_at=datetime(2026, 5, 8, 13, 5, tzinfo=UTC),
            ),
        }
    )
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488911",
            text="Новый неразобранный кандидат",
            score=120,
            temperature="hot",
            review_lane="direct_pur_lead",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            domain_signals=[],
            facts=[],
        )
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    reviewed = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"review_status": "reviewed", "verdict": "not_lead"},
    )

    assert reviewed.status_code == 200
    reviewed_payload = reviewed.json()
    assert reviewed_payload["total"] == 1
    assert reviewed_payload["items"][0]["message_id"] == "488906"
    assert reviewed_payload["items"][0]["auto_is_lead"] is True
    assert reviewed_payload["items"][0]["is_lead"] is False
    assert reviewed_payload["items"][0]["effective_is_lead"] is False
    assert reviewed_payload["items"][0]["review"]["verdict"] == "not_lead"
    assert reviewed_payload["items"][0]["review"]["comment"] == "Нет запроса на подрядчика"

    unreviewed = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"review_status": "unreviewed"},
    )

    assert unreviewed.status_code == 200
    unreviewed_payload = unreviewed.json()
    assert unreviewed_payload["total"] == 1
    assert unreviewed_payload["items"][0]["message_id"] == "488911"
    assert unreviewed_payload["items"][0]["review"] is None


def test_gets_and_updates_analytics_message_review() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    initial = client.get("/api/v1/analytics/messages/488906")

    assert initial.status_code == 200
    assert initial.json()["review"] is None

    update = client.put(
        "/api/v1/analytics/messages/488906/review",
        json={
            "verdict": "not_lead",
            "comment": "Обсуждение лицензий, нет запроса на подрядчика",
            "tags": ["equipment_only", "no_provider_intent"],
        },
    )

    assert update.status_code == 200
    payload = update.json()
    assert payload["review"] == {
        "source_message_id": "488906",
        "verdict": "not_lead",
        "comment": "Обсуждение лицензий, нет запроса на подрядчика",
        "tags": ["equipment_only", "no_provider_intent"],
        "created_at": "2026-05-08T13:00:00Z",
        "updated_at": "2026-05-08T13:05:00Z",
    }


def test_noise_review_overrides_lead_status_and_cancels_unsent_notifications() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    update = client.put(
        "/api/v1/analytics/messages/488906/review",
        json={
            "verdict": "noise",
            "comment": "Продажа оборудования, не лид",
            "tags": ["sale"],
        },
    )

    assert update.status_code == 200
    payload = update.json()
    assert payload["auto_is_lead"] is True
    assert payload["is_lead"] is False
    assert payload["effective_is_lead"] is False
    assert payload["lead_status_source"] == "review"
    assert payload["review"]["verdict"] == "noise"
    assert repository.cancelled_notifications == [("488906", "review:noise")]
