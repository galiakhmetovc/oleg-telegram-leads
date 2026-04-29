from datetime import datetime

import pytest
from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.audit import operational_events_table
from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_terms_table,
    classifier_snapshot_entries_table,
    classifier_versions_table,
)
from pur_leads.models.evaluation import decision_records_table
from pur_leads.models.leads import lead_clusters_table, lead_events_table, lead_matches_table
from pur_leads.models.notifications import notification_events_table
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.settings import SettingsService
from pur_leads.workers.runtime import (
    LeadClassifierMatch,
    LeadClassifierResult,
    WorkerRuntime,
    build_lead_handler_registry,
)


class FakeLeadClassifier:
    def __init__(
        self,
        *,
        classifier_version_id: str,
        snapshot_entry_id: str,
        category_id: str,
        term_id: str,
    ) -> None:
        self.classifier_version_id = classifier_version_id
        self.snapshot_entry_id = snapshot_entry_id
        self.category_id = category_id
        self.term_id = term_id
        self.seen_messages: list[dict] = []
        self.seen_payload: dict | None = None

    async def classify_message_batch(self, *, messages: list, payload: dict):
        self.seen_messages = [
            {
                "source_message_id": message.source_message_id,
                "message_text": message.message_text,
                "sender_id": message.sender_id,
                "telegram_message_id": message.telegram_message_id,
            }
            for message in messages
        ]
        self.seen_payload = payload
        return [
            LeadClassifierResult(
                source_message_id=message.source_message_id,
                classifier_version_id=self.classifier_version_id,
                decision="lead",
                detection_mode="live",
                confidence=0.88,
                commercial_value_score=0.7,
                negative_score=0.02,
                notify_reason="camera request",
                reason="User asks for a camera",
                matches=[
                    LeadClassifierMatch(
                        classifier_snapshot_entry_id=self.snapshot_entry_id,
                        catalog_term_id=self.term_id,
                        category_id=self.category_id,
                        match_type="term",
                        matched_text="камера",
                        score=0.91,
                    )
                ],
            )
            for message in messages
        ]


class PartialLeadClassifier(FakeLeadClassifier):
    async def classify_message_batch(self, *, messages: list, payload: dict):
        results = await super().classify_message_batch(messages=messages, payload=payload)
        return results[:1]


class PayloadModeLeadClassifier(FakeLeadClassifier):
    async def classify_message_batch(self, *, messages: list, payload: dict):
        results = await super().classify_message_batch(messages=messages, payload=payload)
        mode = payload.get("detection_mode", "live")
        return [
            LeadClassifierResult(
                source_message_id=result.source_message_id,
                classifier_version_id=result.classifier_version_id,
                decision=result.decision,
                detection_mode=mode,
                confidence=result.confidence,
                commercial_value_score=result.commercial_value_score,
                negative_score=result.negative_score,
                high_value_signals_json=result.high_value_signals_json,
                negative_signals_json=result.negative_signals_json,
                notify_reason=result.notify_reason,
                reason=result.reason,
                matches=result.matches,
            )
            for result in results
        ]


class ConfigurableLeadClassifier(FakeLeadClassifier):
    def __init__(
        self,
        *,
        decision: str,
        confidence: float,
        commercial_value_score: float | None = None,
        negative_score: float | None = None,
        detection_mode: str = "live",
        classifier_version_id: str,
        snapshot_entry_id: str,
        category_id: str,
        term_id: str,
    ) -> None:
        super().__init__(
            classifier_version_id=classifier_version_id,
            snapshot_entry_id=snapshot_entry_id,
            category_id=category_id,
            term_id=term_id,
        )
        self.decision = decision
        self.confidence = confidence
        self.commercial_value_score = commercial_value_score
        self.negative_score = negative_score
        self.detection_mode = detection_mode

    async def classify_message_batch(self, *, messages: list, payload: dict):
        await super().classify_message_batch(messages=messages, payload=payload)
        return [
            LeadClassifierResult(
                source_message_id=message.source_message_id,
                classifier_version_id=self.classifier_version_id,
                decision=self.decision,
                detection_mode=self.detection_mode,
                confidence=self.confidence,
                commercial_value_score=self.commercial_value_score,
                negative_score=self.negative_score,
                notify_reason="camera request",
                reason="User asks for a camera",
                matches=[
                    LeadClassifierMatch(
                        classifier_snapshot_entry_id=self.snapshot_entry_id,
                        catalog_term_id=self.term_id,
                        category_id=self.category_id,
                        match_type="term",
                        matched_text="камера",
                        score=0.91,
                    )
                ],
            )
            for message in messages
        ]


class FakeShadowLeadClassifier:
    model = "glm-4.5-flash"
    prompt_hash = "shadow-prompt-hash"
    prompt_version = "lead-shadow-v1"

    def __init__(self, *, decision: str = "not_lead", confidence: float = 0.73) -> None:
        self.decision = decision
        self.confidence = confidence
        self.last_token_usage_json = {
            "prompt_tokens": 100,
            "completion_tokens": 30,
            "total_tokens": 130,
            "request_id": "shadow-request",
            "model": self.model,
        }
        self.seen_messages: list[str] = []
        self.seen_payload: dict | None = None

    async def classify_message_batch(self, *, messages: list, payload: dict):
        self.seen_messages = [message.source_message_id for message in messages]
        self.seen_payload = payload
        return [
            LeadClassifierResult(
                source_message_id=message.source_message_id,
                classifier_version_id="",
                decision=self.decision,
                detection_mode=payload.get("detection_mode", "live"),
                confidence=self.confidence,
                commercial_value_score=0.2,
                negative_score=0.1,
                high_value_signals_json=["llm_shadow_signal"],
                negative_signals_json=[],
                notify_reason="llm_shadow_review",
                reason="LLM shadow classified the message",
                matches=[
                    LeadClassifierMatch(
                        match_type="llm_signal",
                        matched_text="llm_shadow_signal",
                        score=self.confidence,
                    )
                ],
            )
            for message in messages
        ]


class FailingShadowLeadClassifier(FakeShadowLeadClassifier):
    async def classify_message_batch(self, *, messages: list, payload: dict):
        raise RuntimeError("shadow unavailable")


class FakeLeadNotifier:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_lead_notification(self, *, chat_id: str, text: str) -> dict:
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 77}


class FailingLeadNotifier:
    async def send_lead_notification(self, *, chat_id: str, text: str) -> dict:
        raise RuntimeError("telegram unavailable")


async def _noop_job_handler(job):
    return {"job_id": job.id}


@pytest.fixture
def runtime_session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        category_id = _insert_category(session)
        term_id = _insert_term(session, category_id)
        classifier_version_id = _insert_classifier_version(session)
        snapshot_entry_id = _insert_snapshot_entry(
            session,
            classifier_version_id,
            category_id=category_id,
            term_id=term_id,
        )
        session.commit()
        yield {
            "session": session,
            "source_id": source_id,
            "category_id": category_id,
            "term_id": term_id,
            "classifier_version_id": classifier_version_id,
            "snapshot_entry_id": snapshot_entry_id,
        }


@pytest.mark.asyncio
async def test_classify_message_batch_handler_records_events_clusters_and_marks_classified(
    runtime_session,
):
    session = runtime_session["session"]
    queued_message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=100,
        sender_id="sender-1",
        text="нужна камера",
        status="queued",
    )
    unclassified_message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=101,
        sender_id="sender-2",
        text="подберите камеру на дачу",
        status="unclassified",
    )
    already_classified_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=102,
        sender_id="sender-3",
        text="уже обработано",
        status="classified",
    )
    classifier = FakeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    job = SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10, "cluster_window_minutes": 45},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(session, classifier=classifier),
    )

    result = await runtime.run_once()

    stored = SchedulerService(session).repository.get(job.id)
    messages = {
        row["id"]: row["classification_status"]
        for row in session.execute(select(source_messages_table)).mappings().all()
    }
    events = session.execute(select(lead_events_table)).mappings().all()
    matches = session.execute(select(lead_matches_table)).mappings().all()
    clusters = session.execute(select(lead_clusters_table)).mappings().all()
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.status == "succeeded"
    assert stored.result_summary_json == {
        "message_count": 2,
        "event_count": 2,
        "cluster_count": 2,
    }
    assert messages[queued_message_id] == "classified"
    assert messages[unclassified_message_id] == "classified"
    assert messages[already_classified_id] == "classified"
    assert {event["source_message_id"] for event in events} == {
        queued_message_id,
        unclassified_message_id,
    }
    assert {match["matched_text"] for match in matches} == {"камера"}
    assert len(clusters) == 2
    assert [message["source_message_id"] for message in classifier.seen_messages] == [
        queued_message_id,
        unclassified_message_id,
    ]
    assert classifier.seen_payload == {"limit": 10, "cluster_window_minutes": 45}


@pytest.mark.asyncio
async def test_classify_lead_queues_context_and_sends_configured_notification(runtime_session):
    session = runtime_session["session"]
    message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=120,
        sender_id="sender-1",
        text="нужна камера на дачу",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = FakeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    notifier = FakeLeadNotifier()
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            notifier=notifier,
        ),
    )

    classify_result = await runtime.run_once()
    notify_result = await runtime.run_once()

    jobs = (
        session.execute(select(scheduler_jobs_table).order_by(scheduler_jobs_table.c.created_at))
        .mappings()
        .all()
    )
    context_jobs = [row for row in jobs if row["job_type"] == "fetch_message_context"]
    notify_jobs = [row for row in jobs if row["job_type"] == "send_notifications"]
    cluster = session.execute(select(lead_clusters_table)).mappings().one()
    notification_event = session.execute(select(notification_events_table)).mappings().one()
    assert classify_result.status == "succeeded"
    assert notify_result.status == "succeeded"
    assert len(context_jobs) == 1
    assert context_jobs[0]["source_message_id"] == message_id
    assert context_jobs[0]["payload_json"] == {"before": 2, "after": 2, "reply_depth": 2}
    assert len(notify_jobs) == 1
    assert notify_jobs[0]["status"] == "succeeded"
    assert notify_jobs[0]["scope_id"] == cluster["id"]
    assert notify_jobs[0]["idempotency_key"] == f"lead-notify:{cluster['id']}"
    assert notify_jobs[0]["payload_json"]["notification_event_id"] == notification_event["id"]
    assert notification_event["status"] == "sent"
    assert notification_event["notification_policy"] == "immediate"
    assert notification_event["notification_type"] == "lead"
    assert notification_event["lead_cluster_id"] == cluster["id"]
    assert notification_event["lead_event_id"] is not None
    assert notification_event["scheduler_job_id"] == notify_jobs[0]["id"]
    assert notification_event["sent_at"] is not None
    assert notifier.sent == [
        {
            "chat_id": "operator-chat",
            "text": (
                "Новый лид: lead (88%)\n"
                "нужна камера на дачу\n"
                "Причина: camera request\n"
                "Источник: https://t.me/test/120"
            ),
        }
    ]
    assert cluster["last_notified_at"] is not None
    assert cluster["notify_update_count"] == 1


@pytest.mark.asyncio
async def test_classify_message_batch_records_llm_shadow_decisions_without_side_effects(
    runtime_session,
):
    session = runtime_session["session"]
    message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=119,
        sender_id="sender-1",
        text="нужна камера для дома",
        status="queued",
    )
    SettingsService(session).set(
        "lead_llm_shadow_enabled",
        True,
        value_type="bool",
        updated_by="admin",
    )
    classifier = FakeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    shadow_classifier = FakeShadowLeadClassifier(decision="not_lead", confidence=0.74)
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            shadow_classifier=shadow_classifier,
        ),
    )

    result = await runtime.run_once()

    events = session.execute(select(lead_events_table)).mappings().all()
    clusters = session.execute(select(lead_clusters_table)).mappings().all()
    decisions = (
        session.execute(
            select(decision_records_table).order_by(decision_records_table.c.decision_type)
        )
        .mappings()
        .all()
    )
    assert result.status == "succeeded"
    assert len(events) == 1
    assert len(clusters) == 1
    assert {row["decision_type"] for row in decisions} == {
        "lead_detection",
        "lead_detection_shadow",
    }
    shadow = next(row for row in decisions if row["decision_type"] == "lead_detection_shadow")
    assert shadow["entity_type"] == "source_message"
    assert shadow["entity_id"] == message_id
    assert shadow["source_message_id"] == message_id
    assert shadow["lead_event_id"] is None
    assert shadow["classifier_version_id"] is None
    assert shadow["model"] == "glm-4.5-flash"
    assert shadow["prompt_version"] == "lead-shadow-v1"
    assert shadow["decision"] == "not_lead"
    assert shadow["confidence"] == 0.74
    assert shadow["input_json"]["shadow_mode"] is True
    assert shadow["input_json"]["message_text"] == "нужна камера для дома"
    assert shadow["evidence_json"]["matches"][0]["matched_text"] == "llm_shadow_signal"
    assert shadow["output_json"]["token_usage"]["total_tokens"] == 130
    assert shadow_classifier.seen_messages == [message_id]
    assert shadow_classifier.seen_payload == {
        "limit": 10,
        "shadow_mode": True,
        "detection_mode": "live",
    }


@pytest.mark.asyncio
async def test_classify_message_batch_continues_when_llm_shadow_fails(runtime_session):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=118,
        sender_id="sender-1",
        text="нужна камера для дома",
        status="queued",
    )
    SettingsService(session).set(
        "lead_llm_shadow_enabled",
        True,
        value_type="bool",
        updated_by="admin",
    )
    classifier = FakeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            shadow_classifier=FailingShadowLeadClassifier(),
        ),
    )

    result = await runtime.run_once()

    events = session.execute(select(lead_events_table)).mappings().all()
    shadow_decisions = (
        session.execute(
            select(decision_records_table).where(
                decision_records_table.c.decision_type == "lead_detection_shadow"
            )
        )
        .mappings()
        .all()
    )
    audit_event = (
        session.execute(
            select(operational_events_table).where(
                operational_events_table.c.event_type == "ai_request",
                operational_events_table.c.entity_type == "lead_detection_shadow",
            )
        )
        .mappings()
        .one()
    )
    assert result.status == "succeeded"
    assert len(events) == 1
    assert shadow_decisions == []
    assert audit_event["severity"] == "warning"
    assert audit_event["details_json"]["reason"] == "shadow_classifier_failed"
    assert audit_event["details_json"]["error"] == "shadow unavailable"


@pytest.mark.asyncio
async def test_classify_maybe_records_web_only_notification_policy_by_default(runtime_session):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=121,
        sender_id="sender-1",
        text="возможно нужна камера",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = ConfigurableLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
        decision="maybe",
        confidence=0.61,
        commercial_value_score=0.3,
    )
    notifier = FakeLeadNotifier()
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            notifier=notifier,
        ),
    )

    result = await runtime.run_once()

    notify_jobs = (
        session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "send_notifications"
            )
        )
        .mappings()
        .all()
    )
    notification_event = session.execute(select(notification_events_table)).mappings().one()
    assert result.status == "succeeded"
    assert notify_jobs == []
    assert notifier.sent == []
    assert notification_event["status"] == "suppressed"
    assert notification_event["notification_type"] == "maybe"
    assert notification_event["notification_policy"] == "suppressed"
    assert notification_event["suppressed_reason"] == "maybe_web_only"


@pytest.mark.asyncio
async def test_classify_low_confidence_live_lead_records_suppressed_notification(
    runtime_session,
):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=122,
        sender_id="sender-1",
        text="может камеру когда-нибудь",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = ConfigurableLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
        decision="lead",
        confidence=0.52,
        commercial_value_score=0.2,
        negative_score=0.1,
    )
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(session, classifier=classifier),
    )

    result = await runtime.run_once()

    notify_jobs = (
        session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "send_notifications"
            )
        )
        .mappings()
        .all()
    )
    notification_event = session.execute(select(notification_events_table)).mappings().one()
    assert result.status == "succeeded"
    assert notify_jobs == []
    assert notification_event["status"] == "suppressed"
    assert notification_event["notification_type"] == "lead"
    assert notification_event["suppressed_reason"] == "confidence_below_threshold"


@pytest.mark.asyncio
async def test_high_value_low_confidence_maybe_can_notify(runtime_session):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=124,
        sender_id="sender-1",
        text="ищу дорогую систему камер",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = ConfigurableLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
        decision="maybe",
        confidence=0.5,
        commercial_value_score=0.82,
        negative_score=0.1,
    )
    notifier = FakeLeadNotifier()
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            notifier=notifier,
        ),
    )

    classify_result = await runtime.run_once()
    notify_result = await runtime.run_once()

    notification_event = session.execute(select(notification_events_table)).mappings().one()
    assert classify_result.status == "succeeded"
    assert notify_result.status == "succeeded"
    assert notification_event["status"] == "sent"
    assert notification_event["notification_type"] == "maybe"
    assert notifier.sent[0]["chat_id"] == "operator-chat"


@pytest.mark.asyncio
async def test_multiple_events_in_same_cluster_queue_one_telegram_notification(runtime_session):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=125,
        sender_id="sender-1",
        text="нужна камера",
        status="queued",
    )
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=126,
        sender_id="sender-1",
        text="и еще регистратор",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = FakeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(session, classifier=classifier),
    )

    result = await runtime.run_once()

    notify_jobs = (
        session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "send_notifications"
            )
        )
        .mappings()
        .all()
    )
    notification_events = (
        session.execute(
            select(notification_events_table).order_by(notification_events_table.c.created_at)
        )
        .mappings()
        .all()
    )
    assert result.status == "succeeded"
    assert len(notify_jobs) == 1
    assert [event["status"] for event in notification_events] == ["queued", "suppressed"]
    assert notification_events[1]["suppressed_reason"] == "cluster_already_has_notification"


@pytest.mark.asyncio
async def test_failed_notification_marks_notification_event_failed(runtime_session):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=123,
        sender_id="sender-1",
        text="срочно нужна камера",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = FakeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            notifier=FailingLeadNotifier(),
        ),
    )

    classify_result = await runtime.run_once()
    notify_result = await runtime.run_once()

    notify_job = (
        session.execute(
            select(scheduler_jobs_table).where(
                scheduler_jobs_table.c.job_type == "send_notifications"
            )
        )
        .mappings()
        .one()
    )
    notification_event = session.execute(select(notification_events_table)).mappings().one()
    assert classify_result.status == "succeeded"
    assert notify_result.status == "failed"
    assert notify_job["status"] == "queued"
    assert "telegram unavailable" in (notify_job["last_error"] or "")
    assert notification_event["status"] == "failed"
    assert notification_event["error"] == "telegram unavailable"


@pytest.mark.asyncio
async def test_classify_message_batch_fails_when_adapter_omits_loaded_messages(runtime_session):
    session = runtime_session["session"]
    first_message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=105,
        sender_id="sender-1",
        text="нужна камера",
        status="queued",
    )
    second_message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=106,
        sender_id="sender-2",
        text="подберите камеру на дачу",
        status="queued",
    )
    classifier = PartialLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    job = SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(session, classifier=classifier),
    )

    result = await runtime.run_once()

    stored = SchedulerService(session).repository.get(job.id)
    messages = {
        row["id"]: row["classification_status"]
        for row in session.execute(select(source_messages_table)).mappings().all()
    }
    assert stored is not None
    assert result.status == "failed"
    assert "missing classifier results" in (stored.last_error or "")
    assert messages[first_message_id] == "queued"
    assert messages[second_message_id] == "queued"
    assert session.execute(select(lead_events_table)).mappings().all() == []


@pytest.mark.asyncio
async def test_classify_message_batch_without_adapter_fails_visibly(runtime_session):
    session = runtime_session["session"]
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=110,
        sender_id="sender-1",
        text="нужна камера",
        status="queued",
    )
    job = SchedulerService(session).enqueue(
        job_type="classify_message_batch",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
    )
    runtime = WorkerRuntime(session, handlers=build_lead_handler_registry(session))

    result = await runtime.run_once()

    stored = SchedulerService(session).repository.get(job.id)
    event = session.execute(select(operational_events_table)).mappings().one()
    assert stored is not None
    assert result.status == "failed"
    assert stored.last_error == "classify_message_batch adapter is not configured"
    assert event["event_type"] == "scheduler"
    assert event["details_json"]["reason"] == "handler_exception"


@pytest.mark.asyncio
async def test_reclassify_messages_creates_retro_clusters_without_telegram_notification(
    runtime_session,
):
    session = runtime_session["session"]
    message_id = _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=130,
        sender_id="sender-1",
        text="нужна камера после обновления каталога",
        status="classified",
    )
    _insert_source_message(
        session,
        runtime_session["source_id"],
        telegram_message_id=131,
        sender_id="sender-2",
        text="новое сообщение еще не трогаем",
        status="queued",
    )
    SettingsService(session).set(
        "telegram_lead_notification_chat_id",
        "operator-chat",
        value_type="string",
        updated_by="admin",
    )
    classifier = PayloadModeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    notifier = FakeLeadNotifier()
    job = SchedulerService(session).enqueue(
        job_type="reclassify_messages",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={"limit": 10, "trigger_reason": "catalog_change"},
    )
    runtime = WorkerRuntime(
        session,
        handlers=build_lead_handler_registry(
            session,
            classifier=classifier,
            notifier=notifier,
        ),
    )

    result = await runtime.run_once()

    stored = SchedulerService(session).repository.get(job.id)
    event = session.execute(select(lead_events_table)).mappings().one()
    cluster = session.execute(select(lead_clusters_table)).mappings().one()
    jobs = (
        session.execute(select(scheduler_jobs_table).order_by(scheduler_jobs_table.c.created_at))
        .mappings()
        .all()
    )
    message_status = session.execute(
        select(source_messages_table.c.classification_status).where(
            source_messages_table.c.id == message_id
        )
    ).scalar_one()
    assert stored is not None
    assert result.status == "succeeded"
    assert stored.result_summary_json == {
        "message_count": 1,
        "event_count": 1,
        "cluster_count": 1,
    }
    assert classifier.seen_payload == {
        "limit": 10,
        "trigger_reason": "catalog_change",
        "classification_statuses": ["classified"],
        "detection_mode": "retro_research",
    }
    assert event["source_message_id"] == message_id
    assert event["detection_mode"] == "retro_research"
    assert event["is_retro"] is True
    assert event["original_detected_at"] is not None
    assert cluster["primary_source_message_id"] == message_id
    assert message_status == "classified"
    assert [row["job_type"] for row in jobs].count("fetch_message_context") == 1
    assert [row["job_type"] for row in jobs].count("send_notifications") == 0
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_reclassify_messages_chains_next_batch_with_cursor(runtime_session):
    session = runtime_session["session"]
    message_ids = [
        _insert_source_message(
            session,
            runtime_session["source_id"],
            telegram_message_id=140 + index,
            sender_id=f"sender-{index}",
            text=f"нужна камера {index}",
            status="classified",
        )
        for index in range(3)
    ]
    classifier = PayloadModeLeadClassifier(
        classifier_version_id=runtime_session["classifier_version_id"],
        snapshot_entry_id=runtime_session["snapshot_entry_id"],
        category_id=runtime_session["category_id"],
        term_id=runtime_session["term_id"],
    )
    SchedulerService(session).enqueue(
        job_type="reclassify_messages",
        scope_type="telegram_source",
        monitored_source_id=runtime_session["source_id"],
        payload_json={
            "limit": 2,
            "trigger_reason": "catalog_change",
            "chain_next_batch": True,
        },
    )
    handlers = build_lead_handler_registry(session, classifier=classifier)
    handlers["fetch_message_context"] = _noop_job_handler
    runtime = WorkerRuntime(session, handlers=handlers)

    first_result = await runtime.run_once()
    run_results = [first_result]
    for _ in range(10):
        result = await runtime.run_once()
        run_results.append(result)
        if result.status == "idle":
            break

    jobs = (
        session.execute(select(scheduler_jobs_table).order_by(scheduler_jobs_table.c.created_at))
        .mappings()
        .all()
    )
    reclassify_jobs = [row for row in jobs if row["job_type"] == "reclassify_messages"]
    events = session.execute(select(lead_events_table)).mappings().all()
    assert first_result.status == "succeeded"
    assert {result.status for result in run_results} <= {"succeeded", "idle"}
    assert len(reclassify_jobs) == 2
    assert reclassify_jobs[0]["status"] == "succeeded"
    assert reclassify_jobs[1]["status"] == "succeeded"
    assert reclassify_jobs[1]["payload_json"]["cursor"]["source_message_id"] == message_ids[1]
    assert reclassify_jobs[1]["payload_json"]["classification_statuses"] == ["classified"]
    assert {event["source_message_id"] for event in events} == set(message_ids)


def _insert_monitored_source(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(monitored_sources_table).values(
            id=row_id,
            source_kind="telegram_supergroup",
            input_ref="@test",
            source_purpose="lead_monitoring",
            priority="normal",
            status="active",
            lead_detection_enabled=True,
            catalog_ingestion_enabled=False,
            phase_enabled=True,
            start_mode="from_now",
            historical_backfill_policy="retro_web_only",
            poll_interval_seconds=60,
            added_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_category(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_categories_table).values(
            id=row_id,
            parent_id=None,
            slug="video",
            name="Video",
            description=None,
            status="approved",
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_term(session, category_id: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(catalog_terms_table).values(
            id=row_id,
            item_id=None,
            category_id=category_id,
            term="камера",
            normalized_term="камера",
            term_type="keyword",
            language="ru",
            status="approved",
            weight=1.0,
            created_by="test",
            first_seen_source_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id


def _insert_classifier_version(session) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_versions_table).values(
            id=row_id,
            version=1,
            created_at=utc_now(),
            created_by="test",
            included_statuses_json=["approved", "auto_pending"],
            catalog_hash="catalog",
            example_hash="example",
            prompt_hash="prompt",
            keyword_index_hash="keyword",
            settings_hash="settings",
        )
    )
    return row_id


def _insert_snapshot_entry(
    session,
    classifier_version_id: str,
    *,
    category_id: str,
    term_id: str,
) -> str:
    row_id = new_id()
    session.execute(
        insert(classifier_snapshot_entries_table).values(
            id=row_id,
            classifier_version_id=classifier_version_id,
            entry_type="term",
            entity_type="term",
            entity_id=term_id,
            status_at_build="approved",
            weight=1.5,
            text_value="камера",
            normalized_value="камера",
            metadata_json={"category_id": category_id},
            content_hash="hash",
            created_at=utc_now(),
        )
    )
    return row_id


def _insert_source_message(
    session,
    source_id: str,
    *,
    telegram_message_id: int,
    sender_id: str,
    text: str,
    status: str,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            telegram_message_id=telegram_message_id,
            sender_id=sender_id,
            message_date=datetime(2026, 4, 28, 12, telegram_message_id % 50, 0),
            text=text,
            caption=None,
            normalized_text=text,
            has_media=False,
            media_metadata_json=None,
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={},
            fetched_at=now,
            classification_status=status,
            archive_pointer_id=None,
            is_archived_stub=False,
            text_archived=False,
            caption_archived=False,
            metadata_archived=False,
            created_at=now,
            updated_at=now,
        )
    )
    return row_id
