"""Decision trace and quality evaluation behavior."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.evaluation import evaluation_results_table
from pur_leads.models.leads import (
    feedback_events_table,
    lead_clusters_table,
    lead_events_table,
    lead_matches_table,
)
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.repositories.evaluation import (
    DecisionRecord,
    EvaluationCaseRecord,
    EvaluationDatasetRecord,
    EvaluationRepository,
    EvaluationResultRecord,
    EvaluationRunRecord,
)

FEEDBACK_REGRESSION_DATASET_KEY = "feedback_regression:lead_detection"
MANUAL_EXAMPLES_DATASET_KEY = "manual_examples:lead_detection"


@dataclass(frozen=True)
class EvaluationResultInput:
    actual_decision: str | None = None
    actual_category_id: str | None = None
    actual_catalog_item_ids_json: Any | None = None
    actual_notification_policy: str | None = None
    actual_cluster_behavior: str | None = None
    actual_crm_candidate_json: Any | None = None
    passed: bool = False
    failure_type: str | None = None
    details_json: Any | None = None
    decision_record_id: str | None = None


class EvaluationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = EvaluationRepository(session)

    def record_decision(
        self,
        *,
        decision_type: str,
        entity_type: str,
        entity_id: str,
        decision: str,
        created_by: str,
        dedupe_key: str | None = None,
        source_message_id: str | None = None,
        lead_event_id: str | None = None,
        lead_cluster_id: str | None = None,
        source_id: str | None = None,
        classifier_version_id: str | None = None,
        catalog_version_id: str | None = None,
        catalog_hash: str | None = None,
        prompt_hash: str | None = None,
        prompt_version: str | None = None,
        model: str | None = None,
        settings_hash: str | None = None,
        confidence: float | None = None,
        reason: str | None = None,
        input_json: Any | None = None,
        evidence_json: Any | None = None,
        output_json: Any | None = None,
        status: str = "active",
    ) -> DecisionRecord:
        if dedupe_key is not None:
            existing = self.repository.find_decision_by_dedupe_key(dedupe_key)
            if existing is not None:
                return existing

        record = self.repository.create_decision(
            decision_type=decision_type,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_key=dedupe_key,
            source_message_id=source_message_id,
            lead_event_id=lead_event_id,
            lead_cluster_id=lead_cluster_id,
            source_id=source_id,
            classifier_version_id=classifier_version_id,
            catalog_version_id=catalog_version_id,
            catalog_hash=catalog_hash,
            prompt_hash=prompt_hash,
            prompt_version=prompt_version,
            model=model,
            settings_hash=settings_hash,
            decision=decision,
            confidence=confidence,
            reason=reason,
            input_json=input_json,
            evidence_json=evidence_json,
            output_json=output_json,
            status=status,
            created_by=created_by,
            created_at=utc_now(),
        )
        self.session.commit()
        return record

    def get_or_create_feedback_regression_dataset(
        self,
        *,
        created_by: str,
    ) -> EvaluationDatasetRecord:
        existing = self.repository.find_dataset_by_key(FEEDBACK_REGRESSION_DATASET_KEY)
        if existing is not None:
            return existing

        now = utc_now()
        dataset = self.repository.create_dataset(
            dataset_key=FEEDBACK_REGRESSION_DATASET_KEY,
            name="Feedback regression: lead detection",
            dataset_type="feedback_regression",
            description="Lead detection regression cases promoted from operator feedback.",
            status="active",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.commit()
        return dataset

    def get_or_create_manual_examples_dataset(
        self,
        *,
        created_by: str,
    ) -> EvaluationDatasetRecord:
        existing = self.repository.find_dataset_by_key(MANUAL_EXAMPLES_DATASET_KEY)
        if existing is not None:
            return existing

        now = utc_now()
        dataset = self.repository.create_dataset(
            dataset_key=MANUAL_EXAMPLES_DATASET_KEY,
            name="Manual examples: lead detection",
            dataset_type="golden",
            description="Lead detection cases manually submitted by Oleg or an admin.",
            status="active",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.commit()
        return dataset

    def create_manual_lead_case(
        self,
        *,
        expected_decision: str,
        message_text: str,
        actor: str,
        manual_input_id: str,
        classifier_example_id: str | None = None,
        source_id: str | None = None,
        source_message_id: str | None = None,
        evidence_note: str | None = None,
        input_type: str | None = None,
        url: str | None = None,
    ) -> EvaluationCaseRecord:
        dataset = self.get_or_create_manual_examples_dataset(created_by=actor)
        return self.create_case(
            evaluation_dataset_id=dataset.id,
            source_message_id=source_message_id,
            source_id=source_id,
            message_text=message_text,
            context_json={
                "manual_input_id": manual_input_id,
                "classifier_example_id": classifier_example_id,
                "evidence_note": evidence_note,
                "input_type": input_type,
                "url": url,
            },
            expected_decision=expected_decision,
            label_source="manual",
            created_by=actor,
        )

    def create_case(
        self,
        *,
        evaluation_dataset_id: str,
        label_source: str,
        created_by: str,
        source_message_id: str | None = None,
        lead_cluster_id: str | None = None,
        lead_event_id: str | None = None,
        feedback_event_id: str | None = None,
        source_id: str | None = None,
        message_text: str | None = None,
        context_json: Any | None = None,
        expected_decision: str | None = None,
        expected_category_id: str | None = None,
        expected_catalog_item_ids_json: Any | None = None,
        expected_reason_code: str | None = None,
        expected_notification_policy: str | None = None,
        expected_cluster_behavior: str | None = None,
        expected_crm_candidate_json: Any | None = None,
    ) -> EvaluationCaseRecord:
        now = utc_now()
        case = self.repository.create_case(
            evaluation_dataset_id=evaluation_dataset_id,
            source_message_id=source_message_id,
            lead_cluster_id=lead_cluster_id,
            lead_event_id=lead_event_id,
            feedback_event_id=feedback_event_id,
            source_id=source_id,
            message_text=message_text,
            context_json=context_json or {},
            expected_decision=expected_decision,
            expected_category_id=expected_category_id,
            expected_catalog_item_ids_json=expected_catalog_item_ids_json,
            expected_reason_code=expected_reason_code,
            expected_notification_policy=expected_notification_policy,
            expected_cluster_behavior=expected_cluster_behavior,
            expected_crm_candidate_json=expected_crm_candidate_json,
            label_source=label_source,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.commit()
        return case

    def promote_feedback_to_regression_case(
        self,
        feedback_event_id: str,
        *,
        actor: str,
    ) -> EvaluationCaseRecord:
        dataset = self.get_or_create_feedback_regression_dataset(created_by=actor)
        existing = self.repository.find_case_by_dataset_feedback(
            evaluation_dataset_id=dataset.id,
            feedback_event_id=feedback_event_id,
        )
        if existing is not None:
            return existing

        feedback = self._feedback(feedback_event_id)
        context = self._context_for_feedback(feedback)
        return self.create_case(
            evaluation_dataset_id=dataset.id,
            source_message_id=context.get("source_message_id"),
            lead_cluster_id=context.get("lead_cluster_id"),
            lead_event_id=context.get("lead_event_id"),
            feedback_event_id=feedback_event_id,
            source_id=context.get("source_id"),
            message_text=context.get("message_text"),
            context_json={
                "feedback": {
                    "id": feedback["id"],
                    "target_type": feedback["target_type"],
                    "target_id": feedback["target_id"],
                    "action": feedback["action"],
                    "reason_code": feedback["reason_code"],
                    "feedback_scope": feedback["feedback_scope"],
                    "learning_effect": feedback["learning_effect"],
                },
                "target": context.get("target"),
            },
            expected_decision=_expected_decision_for_feedback(feedback),
            expected_category_id=context.get("category_id"),
            expected_reason_code=feedback["reason_code"],
            label_source="feedback",
            created_by=actor,
        )

    def start_run(
        self,
        *,
        evaluation_dataset_id: str,
        run_type: str,
        created_by: str,
        classifier_version_id: str | None = None,
        catalog_hash: str | None = None,
        prompt_hash: str | None = None,
        model: str | None = None,
        settings_hash: str | None = None,
    ) -> EvaluationRunRecord:
        now = utc_now()
        run = self.repository.create_run(
            evaluation_dataset_id=evaluation_dataset_id,
            run_type=run_type,
            classifier_version_id=classifier_version_id,
            catalog_hash=catalog_hash,
            prompt_hash=prompt_hash,
            model=model,
            settings_hash=settings_hash,
            status="running",
            started_at=now,
            finished_at=None,
            metrics_json=None,
            error=None,
            created_by=created_by,
            created_at=now,
        )
        self.session.commit()
        return run

    def record_result(
        self,
        *,
        evaluation_run_id: str,
        evaluation_case_id: str,
        result: EvaluationResultInput,
    ) -> EvaluationResultRecord:
        existing = self.repository.find_result_by_run_case(
            evaluation_run_id=evaluation_run_id,
            evaluation_case_id=evaluation_case_id,
        )
        if existing is not None:
            return existing

        record = self.repository.create_result(
            evaluation_run_id=evaluation_run_id,
            evaluation_case_id=evaluation_case_id,
            decision_record_id=result.decision_record_id,
            actual_decision=result.actual_decision,
            actual_category_id=result.actual_category_id,
            actual_catalog_item_ids_json=result.actual_catalog_item_ids_json,
            actual_notification_policy=result.actual_notification_policy,
            actual_cluster_behavior=result.actual_cluster_behavior,
            actual_crm_candidate_json=result.actual_crm_candidate_json,
            passed=result.passed,
            failure_type=result.failure_type,
            details_json=result.details_json or {},
            created_at=utc_now(),
        )
        self.session.commit()
        return record

    def complete_run(self, evaluation_run_id: str) -> EvaluationRunRecord:
        metrics = self._run_metrics(evaluation_run_id)
        run = self.repository.update_run(
            evaluation_run_id,
            status="completed",
            finished_at=utc_now(),
            metrics_json=metrics,
            error=None,
        )
        self.session.commit()
        return run

    def _feedback(self, feedback_event_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(feedback_events_table).where(feedback_events_table.c.id == feedback_event_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(feedback_event_id)
        return dict(row)

    def _context_for_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        target_type = feedback["target_type"]
        target_id = feedback["target_id"]
        if target_type == "lead_event":
            return self._context_for_lead_event(target_id, target={"type": target_type})
        if target_type == "lead_cluster":
            cluster = self._lead_cluster(target_id)
            lead_event_id = cluster.get("primary_lead_event_id")
            if lead_event_id:
                return self._context_for_lead_event(
                    lead_event_id,
                    target={"type": target_type, "id": target_id},
                    lead_cluster_id=target_id,
                )
            return {"lead_cluster_id": target_id, "target": {"type": target_type, "id": target_id}}
        if target_type == "lead_match":
            match = self._lead_match(target_id)
            return self._context_for_lead_event(
                match["lead_event_id"],
                target={"type": target_type, "id": target_id},
                category_id=match["category_id"],
            )
        return {"target": {"type": target_type, "id": target_id}}

    def _context_for_lead_event(
        self,
        lead_event_id: str,
        *,
        target: dict[str, Any],
        lead_cluster_id: str | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        event = self._lead_event(lead_event_id)
        message = self._source_message(event["source_message_id"])
        return {
            "source_message_id": event["source_message_id"],
            "lead_event_id": event["id"],
            "lead_cluster_id": lead_cluster_id or event["lead_cluster_id"],
            "source_id": event["raw_source_id"],
            "message_text": event["message_text"] or _message_text(message),
            "category_id": category_id,
            "target": {"id": target.get("id", event["id"]), **target},
        }

    def _lead_event(self, lead_event_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(lead_events_table).where(lead_events_table.c.id == lead_event_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(lead_event_id)
        return dict(row)

    def _lead_cluster(self, lead_cluster_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(lead_clusters_table).where(lead_clusters_table.c.id == lead_cluster_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(lead_cluster_id)
        return dict(row)

    def _lead_match(self, lead_match_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(lead_matches_table).where(lead_matches_table.c.id == lead_match_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(lead_match_id)
        return dict(row)

    def _source_message(self, source_message_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                select(source_messages_table).where(source_messages_table.c.id == source_message_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(source_message_id)
        return dict(row)

    def _run_metrics(self, evaluation_run_id: str) -> dict[str, Any]:
        rows = (
            self.session.execute(
                select(evaluation_results_table.c.passed, evaluation_results_table.c.failure_type)
                .where(evaluation_results_table.c.evaluation_run_id == evaluation_run_id)
                .order_by(evaluation_results_table.c.created_at.asc())
            )
            .mappings()
            .all()
        )
        total = len(rows)
        passed = sum(1 for row in rows if row["passed"])
        failure_types = _failure_type_counts(rows)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total else None,
            "failure_types": failure_types,
        }


def _expected_decision_for_feedback(feedback: dict[str, Any]) -> str | None:
    action = feedback["action"]
    learning_effect = feedback["learning_effect"]
    if action == "lead_confirmed" or learning_effect == "positive_example":
        return "lead"
    if action == "maybe":
        return "maybe"
    if action == "not_lead" or learning_effect in {"negative_example", "match_correction"}:
        return "not_lead"
    return None


def _message_text(message: dict[str, Any]) -> str | None:
    parts = [part for part in (message.get("text"), message.get("caption")) if part]
    return "\n".join(parts) if parts else None


def _failure_type_counts(rows: Sequence[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        failure_type = row["failure_type"]
        if not row["passed"] and failure_type:
            counts[failure_type] = counts.get(failure_type, 0) + 1
    return counts
