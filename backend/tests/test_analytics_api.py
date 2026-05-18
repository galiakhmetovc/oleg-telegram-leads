from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.analytics import get_analytics_repository
from app.domain.analytics import AnalyticsAggregate, AnalyticsCandidate, AnalyticsCandidateLlmSummary, AnalyticsCandidatePage
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
                label="Прямой лид",
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
        score_max: int | None = None,
        q: str | None,
        message_id: str | None = None,
        source_chat: str | None = None,
        source_chat_id: str | None = None,
        source_input_ref: str | None = None,
        source_chat_status: str | None = None,
        telegram_message_id: int | None = None,
        telegram_chat_id: str | None = None,
        sender: str | None = None,
        source_account_id: str | None = None,
        received_from: datetime | None = None,
        received_to: datetime | None = None,
        review_status: str | None = None,
        verdict: AnalyticsReviewVerdict | None = None,
        source_type: str | None = None,
        llm_processed: bool | None = None,
        llm_status: str | None = None,
        llm_verdict: str | None = None,
        llm_recommendation: str | None = None,
        llm_model: str | None = None,
        llm_route: str | None = None,
        llm_agrees_with_rules: bool | None = None,
        llm_has_error: bool | None = None,
        llm_confidence_min: float | None = None,
        llm_confidence_max: float | None = None,
        llm_attempts_min: int | None = None,
        llm_attempts_max: int | None = None,
        enrichment_status: str | None = None,
        sort_by: str | None = None,
        sort_direction: str | None = None,
        grid_filters: list[dict[str, str]] | None = None,
    ) -> AnalyticsCandidatePage:
        items = self.candidates
        if source_type is not None:
            items = [item for item in items if item.source_type == source_type]
        if score_min is not None:
            items = [item for item in items if item.score >= score_min]
        if score_max is not None:
            items = [item for item in items if item.score <= score_max]
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
        if source_chat is not None:
            needle = source_chat.lower()
            items = [
                item
                for item in items
                if needle in (item.source_chat_title or "").lower()
                or needle in (item.source_chat_id or "").lower()
                or needle in (item.source_input_ref or "").lower()
            ]
        if message_id is not None:
            items = [item for item in items if message_id in item.message_id]
        if source_input_ref is not None:
            items = [item for item in items if source_input_ref.lower() in (item.source_input_ref or "").lower()]
        if source_chat_status is not None:
            items = [
                item
                for item in items
                if source_chat_status.lower() in (item.source_chat_status or "").lower()
            ]
        if telegram_message_id is not None:
            items = [item for item in items if item.telegram_message_id == telegram_message_id]
        if telegram_chat_id is not None:
            items = [item for item in items if telegram_chat_id in (item.telegram_chat_id or "")]
        if sender is not None:
            needle = sender.removeprefix("@").lower()
            items = [
                item
                for item in items
                if needle in (item.sender_username or "").lower() or needle in (item.sender_id or "").lower()
            ]
        if source_account_id is not None:
            items = [item for item in items if source_account_id in (item.source_account_id or "")]
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
        if llm_processed is not None:
            items = [item for item in items if bool(item.llm and item.llm.processed) is llm_processed]
        if llm_status is not None:
            items = [item for item in items if item.llm is not None and item.llm.status == llm_status]
        if llm_verdict is not None:
            items = [item for item in items if item.llm is not None and item.llm.verdict == llm_verdict]
        if llm_recommendation is not None:
            items = [item for item in items if item.llm is not None and item.llm.recommendation == llm_recommendation]
        if llm_model is not None:
            items = [item for item in items if item.llm is not None and item.llm.model == llm_model]
        if llm_route is not None:
            items = [item for item in items if item.llm is not None and item.llm.route_id == llm_route]
        if llm_agrees_with_rules is not None:
            items = [
                item
                for item in items
                if item.llm is not None and item.llm.agrees_with_rule_engine is llm_agrees_with_rules
            ]
        if llm_has_error is not None:
            items = [item for item in items if bool(item.llm and item.llm.has_error) is llm_has_error]
        if llm_confidence_min is not None:
            items = [item for item in items if item.llm and item.llm.confidence is not None and item.llm.confidence >= llm_confidence_min]
        if llm_confidence_max is not None:
            items = [item for item in items if item.llm and item.llm.confidence is not None and item.llm.confidence <= llm_confidence_max]
        if llm_attempts_min is not None:
            items = [item for item in items if item.llm and item.llm.attempts is not None and item.llm.attempts >= llm_attempts_min]
        if llm_attempts_max is not None:
            items = [item for item in items if item.llm and item.llm.attempts is not None and item.llm.attempts <= llm_attempts_max]
        if enrichment_status is not None:
            items = [item for item in items if item.enrichment_status == enrichment_status]
        items = sorted(items, key=lambda item: _candidate_sort_key(item, sort_by), reverse=sort_direction != "asc")
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


def _candidate_sort_key(candidate: AnalyticsCandidate, sort_by: str | None) -> object:
    if sort_by == "score":
        return candidate.score
    if sort_by == "sourceChat":
        return candidate.source_chat_title or ""
    if sort_by == "sender":
        return candidate.sender_username or candidate.sender_id or ""
    if sort_by == "llmConfidence":
        return candidate.llm.confidence if candidate.llm and candidate.llm.confidence is not None else -1.0
    if sort_by == "enrichmentStatus":
        return candidate.enrichment_status or ""
    return (
        candidate.received_at is not None,
        candidate.received_at or datetime.min.replace(tzinfo=UTC),
        candidate.message_id,
        candidate.score,
    )


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
    assert payload["items"][0]["source_type"] == "telegram"


def test_lists_analytics_candidates_with_message_source_and_llm_summary_filters() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates[0] = AnalyticsCandidate(
        **{
            **repository.candidates[0].__dict__,
            "message_date": datetime(2026, 5, 8, 12, 29, tzinfo=UTC),
            "sender_id": "101",
            "sender_username": "designer_user",
            "source_input_ref": "@designers",
            "source_chat_status": "active",
            "source_chat_enabled": True,
            "source_account_id": "account-1",
            "raw_payload": {"id": 488906, "peer_id": "designers"},
            "enrichment_status": "completed",
            "enrichment_finished_at": datetime(2026, 5, 8, 12, 31, tzinfo=UTC),
            "llm": AnalyticsCandidateLlmSummary(
                processed=True,
                latest_run_id="llm-run-1",
                status="completed",
                verdict="lead",
                confidence=0.86,
                recommendation="keep",
                agrees_with_rule_engine=True,
                model="lead-qwen-ru",
                route_id="manual",
                attempts=1,
                has_error=False,
                error=None,
                created_at=datetime(2026, 5, 8, 12, 40, tzinfo=UTC),
                updated_at=datetime(2026, 5, 8, 12, 41, tzinfo=UTC),
            ),
        }
    )
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488912",
            text="Пока без LLM",
            score=100,
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
        params={
            "source_type": "telegram",
            "llm_processed": "true",
            "llm_status": "completed",
            "llm_verdict": "lead",
            "llm_recommendation": "keep",
            "llm_model": "lead-qwen-ru",
            "llm_route": "manual",
            "llm_agrees_with_rules": "true",
            "llm_has_error": "false",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["message_id"] == "488906"
    assert item["source_type"] == "telegram"
    assert item["message_date"] == "2026-05-08T12:29:00Z"
    assert item["sender_id"] == "101"
    assert item["sender_username"] == "designer_user"
    assert item["source_input_ref"] == "@designers"
    assert item["source_chat_status"] == "active"
    assert item["source_chat_enabled"] is True
    assert item["source_account_id"] == "account-1"
    assert item["raw_payload"] == {"id": 488906, "peer_id": "designers"}
    assert item["enrichment_status"] == "completed"
    assert item["enrichment_finished_at"] == "2026-05-08T12:31:00Z"
    assert item["llm"] == {
        "processed": True,
        "latest_run_id": "llm-run-1",
        "status": "completed",
        "verdict": "lead",
        "confidence": 0.86,
        "recommendation": "keep",
        "agrees_with_rule_engine": True,
        "model": "lead-qwen-ru",
        "route_id": "manual",
        "attempts": 1,
        "has_error": False,
        "error": None,
        "created_at": "2026-05-08T12:40:00Z",
        "updated_at": "2026-05-08T12:41:00Z",
    }


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


def test_lists_analytics_candidates_newest_first_by_received_at() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates.append(
        AnalyticsCandidate(
            run_id=repository.run_id,
            message_id="488911",
            text="Более новое сообщение с меньшим score",
            score=120,
            temperature="warm",
            review_lane="domain_interest",
            solution_areas=[],
            customer_segments=[],
            intent_signals=[],
            noise_signals=[],
            reasons=[],
            domain_signals=[],
            facts=[],
            received_at=datetime(2026, 5, 8, 12, 45, tzinfo=UTC),
            source_chat_id="designers",
            source_chat_title="Чат дизайнеров",
        )
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"limit": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["message_id"] for item in payload["items"]] == ["488911", "488906"]


def test_lists_analytics_candidates_with_table_column_filters_and_sorting() -> None:
    repository = ApiInMemoryAnalyticsRepository()
    repository.candidates.extend(
        [
            AnalyticsCandidate(
                run_id=repository.run_id,
                message_id="488920",
                text="Биржа строителей, нужен подрядчик на слаботочку",
                score=20,
                temperature="warm",
                review_lane="domain_interest",
                solution_areas=[],
                customer_segments=[],
                intent_signals=[],
                noise_signals=[],
                reasons=[],
                domain_signals=[],
                facts=[],
                received_at=datetime(2026, 5, 8, 12, 45, tzinfo=UTC),
                sender_id="201",
                sender_username="boris_pm",
                source_chat_id="stroy",
                source_chat_title="Биржа строителей",
                source_input_ref="@stroy",
                telegram_chat_id="-1001",
                telegram_message_id=99,
                source_account_id="account-1",
                enrichment_status="failed",
                llm=AnalyticsCandidateLlmSummary(
                    processed=True,
                    status="completed",
                    confidence=0.4,
                    attempts=1,
                    has_error=False,
                ),
            ),
            AnalyticsCandidate(
                run_id=repository.run_id,
                message_id="488921",
                text="Биржа строителей, нужен проектировщик",
                score=180,
                temperature="hot",
                review_lane="direct_pur_lead",
                solution_areas=[],
                customer_segments=[],
                intent_signals=[],
                noise_signals=[],
                reasons=[],
                domain_signals=[],
                facts=[],
                received_at=datetime(2026, 5, 8, 12, 50, tzinfo=UTC),
                sender_id="202",
                sender_username="boris_pm",
                source_chat_id="stroy",
                source_chat_title="Биржа строителей",
                source_input_ref="@stroy",
                telegram_chat_id="-1001",
                telegram_message_id=100,
                source_account_id="account-1",
                enrichment_status="failed",
                llm=AnalyticsCandidateLlmSummary(
                    processed=True,
                    status="completed",
                    confidence=0.9,
                    attempts=2,
                    has_error=False,
                ),
            ),
        ]
    )
    app = create_app()
    app.dependency_overrides[get_analytics_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={
            "source_chat": "биржа",
            "sender": "@boris",
            "source_input_ref": "@stroy",
            "telegram_chat_id": "-1001",
            "source_account_id": "account-1",
            "enrichment_status": "failed",
            "llm_confidence_min": "0.3",
            "llm_attempts_min": "1",
            "sort_by": "score",
            "sort_direction": "asc",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["message_id"] for item in payload["items"]] == ["488920", "488921"]

    exact_message = client.get(
        f"/api/v1/analytics/runs/{repository.run_id}/candidates",
        params={"telegram_message_id": "99"},
    )

    assert exact_message.status_code == 200
    exact_payload = exact_message.json()
    assert exact_payload["total"] == 1
    assert exact_payload["items"][0]["message_id"] == "488920"


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
