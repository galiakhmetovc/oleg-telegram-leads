from datetime import datetime

from sqlalchemy import insert, select

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.models.catalog import classifier_versions_table
from pur_leads.models.evaluation import (
    decision_records_table,
    evaluation_cases_table,
    evaluation_datasets_table,
    evaluation_results_table,
    evaluation_runs_table,
)
from pur_leads.models.leads import feedback_events_table, lead_events_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.evaluation import EvaluationResultInput, EvaluationService


def test_evaluation_service_records_decision_and_deduplicates_by_key(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        message_id = _insert_source_message(session, source_id)
        classifier_version_id = _insert_classifier_version(session)
        session.commit()

        service = EvaluationService(session)
        first = service.record_decision(
            decision_type="lead_detection",
            entity_type="lead_event",
            entity_id="lead-1",
            decision="lead",
            created_by="system",
            dedupe_key="lead_detection:lead-1",
            source_message_id=message_id,
            classifier_version_id=classifier_version_id,
            confidence=0.91,
            reason="User asks for a camera",
            input_json={"text": "нужна камера на дачу"},
            evidence_json={"matches": [{"term": "камера", "score": 0.9}]},
            output_json={"notify": True},
        )
        second = service.record_decision(
            decision_type="lead_detection",
            entity_type="lead_event",
            entity_id="lead-1",
            decision="lead",
            created_by="system",
            dedupe_key="lead_detection:lead-1",
        )

        rows = session.execute(select(decision_records_table)).mappings().all()
        assert second.id == first.id
        assert len(rows) == 1
        assert rows[0]["source_message_id"] == message_id
        assert rows[0]["classifier_version_id"] == classifier_version_id
        assert rows[0]["confidence"] == 0.91
        assert rows[0]["input_json"] == {"text": "нужна камера на дачу"}
        assert rows[0]["evidence_json"]["matches"][0]["term"] == "камера"


def test_evaluation_service_promotes_feedback_to_regression_case_idempotently(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        source_id = _insert_monitored_source(session)
        message_id = _insert_source_message(session, source_id)
        classifier_version_id = _insert_classifier_version(session)
        lead_event_id = _insert_lead_event(session, source_id, message_id, classifier_version_id)
        feedback_id = _insert_feedback(
            session,
            target_type="lead_event",
            target_id=lead_event_id,
            action="not_lead",
            reason_code="expert_or_advice",
            learning_effect="negative_example",
        )
        session.commit()

        service = EvaluationService(session)
        first = service.promote_feedback_to_regression_case(feedback_id, actor="oleg")
        second = service.promote_feedback_to_regression_case(feedback_id, actor="oleg")

        datasets = session.execute(select(evaluation_datasets_table)).mappings().all()
        cases = session.execute(select(evaluation_cases_table)).mappings().all()
        assert second.id == first.id
        assert len(datasets) == 1
        assert datasets[0]["dataset_key"] == "feedback_regression:lead_detection"
        assert len(cases) == 1
        assert cases[0]["evaluation_dataset_id"] == datasets[0]["id"]
        assert cases[0]["feedback_event_id"] == feedback_id
        assert cases[0]["lead_event_id"] == lead_event_id
        assert cases[0]["source_message_id"] == message_id
        assert cases[0]["message_text"] == "нужна камера на дачу"
        assert cases[0]["expected_decision"] == "not_lead"
        assert cases[0]["expected_reason_code"] == "expert_or_advice"
        assert cases[0]["label_source"] == "feedback"
        assert cases[0]["context_json"]["feedback"]["action"] == "not_lead"


def test_evaluation_service_records_run_results_and_metrics(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        service = EvaluationService(session)
        dataset = service.get_or_create_feedback_regression_dataset(created_by="test")
        case = service.create_case(
            evaluation_dataset_id=dataset.id,
            label_source="manual",
            created_by="test",
            message_text="ищу камеру",
            expected_decision="lead",
        )
        run = service.start_run(
            evaluation_dataset_id=dataset.id,
            run_type="lead_detection",
            created_by="test",
            classifier_version_id=None,
            catalog_hash="catalog",
            prompt_hash="prompt",
            model="glm-test",
            settings_hash="settings",
        )
        result = service.record_result(
            evaluation_run_id=run.id,
            evaluation_case_id=case.id,
            result=EvaluationResultInput(
                actual_decision="not_lead",
                passed=False,
                failure_type="false_negative",
                details_json={"reason": "missed camera intent"},
            ),
        )
        completed = service.complete_run(run.id)

        run_row = (
            session.execute(
                select(evaluation_runs_table).where(evaluation_runs_table.c.id == run.id)
            )
            .mappings()
            .one()
        )
        result_row = (
            session.execute(
                select(evaluation_results_table).where(evaluation_results_table.c.id == result.id)
            )
            .mappings()
            .one()
        )
        assert completed.status == "completed"
        assert run_row["metrics_json"] == {
            "total": 1,
            "passed": 0,
            "failed": 1,
            "pass_rate": 0.0,
            "failure_types": {"false_negative": 1},
        }
        assert result_row["actual_decision"] == "not_lead"
        assert result_row["failure_type"] == "false_negative"


def _session_factory(tmp_path):
    engine = create_sqlite_engine(tmp_path / "test.db")
    upgrade_database(engine)
    return create_session_factory(engine)


def _insert_monitored_source(session) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(monitored_sources_table).values(
            id=row_id,
            source_kind="telegram_supergroup",
            telegram_id="-100123456",
            username="test",
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


def _insert_source_message(session, source_id: str) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(source_messages_table).values(
            id=row_id,
            monitored_source_id=source_id,
            telegram_message_id=100,
            sender_id="sender-1",
            message_date=datetime(2026, 4, 28, 12, 0, 0),
            text="нужна камера на дачу",
            caption=None,
            normalized_text="нужна камера на дачу",
            has_media=False,
            media_metadata_json=None,
            reply_to_message_id=None,
            thread_id=None,
            forward_metadata_json=None,
            raw_metadata_json={},
            fetched_at=now,
            classification_status="pending",
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


def _insert_lead_event(
    session,
    source_id: str,
    message_id: str,
    classifier_version_id: str,
) -> str:
    row_id = new_id()
    now = utc_now()
    session.execute(
        insert(lead_events_table).values(
            id=row_id,
            source_message_id=message_id,
            monitored_source_id=source_id,
            raw_source_id=None,
            chat_id="-100123456",
            telegram_message_id=100,
            message_url="https://t.me/test/100",
            sender_id="sender-1",
            sender_name="Ivan",
            message_text="нужна камера на дачу",
            lead_cluster_id=None,
            detected_at=now,
            classifier_version_id=classifier_version_id,
            decision="lead",
            detection_mode="live",
            confidence=0.91,
            commercial_value_score=0.7,
            negative_score=0.05,
            high_value_signals_json=None,
            negative_signals_json=None,
            notify_reason="lead",
            reason="User asks for a camera",
            event_status="active",
            event_review_status="unreviewed",
            duplicate_of_lead_event_id=None,
            is_retro=False,
            original_detected_at=None,
            created_at=now,
        )
    )
    return row_id


def _insert_feedback(
    session,
    *,
    target_type: str,
    target_id: str,
    action: str,
    reason_code: str,
    learning_effect: str,
) -> str:
    row_id = new_id()
    session.execute(
        insert(feedback_events_table).values(
            id=row_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            reason_code=reason_code,
            feedback_scope="classifier",
            learning_effect=learning_effect,
            application_status="recorded",
            applied_entity_type=None,
            applied_entity_id=None,
            applied_at=None,
            comment="not a buyer",
            created_by="oleg",
            created_at=utc_now(),
            metadata_json={},
        )
    )
    return row_id
