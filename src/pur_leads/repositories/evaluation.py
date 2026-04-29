"""Decision trace and evaluation persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.models.evaluation import (
    decision_records_table,
    evaluation_cases_table,
    evaluation_datasets_table,
    evaluation_results_table,
    evaluation_runs_table,
    quality_metric_snapshots_table,
)


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    decision_type: str
    entity_type: str
    entity_id: str
    dedupe_key: str | None
    source_message_id: str | None
    lead_event_id: str | None
    lead_cluster_id: str | None
    source_id: str | None
    classifier_version_id: str | None
    catalog_version_id: str | None
    catalog_hash: str | None
    prompt_hash: str | None
    prompt_version: str | None
    model: str | None
    settings_hash: str | None
    decision: str
    confidence: float | None
    reason: str | None
    input_json: Any
    evidence_json: Any
    output_json: Any
    status: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class EvaluationDatasetRecord:
    id: str
    dataset_key: str
    name: str
    dataset_type: str
    description: str | None
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvaluationCaseRecord:
    id: str
    evaluation_dataset_id: str
    source_message_id: str | None
    lead_cluster_id: str | None
    lead_event_id: str | None
    feedback_event_id: str | None
    source_id: str | None
    message_text: str | None
    context_json: Any
    expected_decision: str | None
    expected_category_id: str | None
    expected_catalog_item_ids_json: Any
    expected_reason_code: str | None
    expected_notification_policy: str | None
    expected_cluster_behavior: str | None
    expected_crm_candidate_json: Any
    label_source: str
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvaluationRunRecord:
    id: str
    evaluation_dataset_id: str
    run_type: str
    classifier_version_id: str | None
    catalog_hash: str | None
    prompt_hash: str | None
    model: str | None
    settings_hash: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    metrics_json: Any
    error: str | None
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class EvaluationResultRecord:
    id: str
    evaluation_run_id: str
    evaluation_case_id: str
    decision_record_id: str | None
    actual_decision: str | None
    actual_category_id: str | None
    actual_catalog_item_ids_json: Any
    actual_notification_policy: str | None
    actual_cluster_behavior: str | None
    actual_crm_candidate_json: Any
    passed: bool
    failure_type: str | None
    details_json: Any
    created_at: datetime


@dataclass(frozen=True)
class QualityMetricSnapshotRecord:
    id: str
    scope: str
    scope_id: str | None
    period_start: datetime | None
    period_end: datetime | None
    precision: float | None
    recall: float | None
    f1: float | None
    false_positive_count: int
    false_negative_count: int
    maybe_count: int
    maybe_resolution_rate: float | None
    high_value_precision: float | None
    retro_precision: float | None
    telegram_notification_precision: float | None
    catalog_candidate_accept_rate: float | None
    catalog_candidate_reject_rate: float | None
    feedback_count: int
    metrics_json: Any
    created_at: datetime


class EvaluationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_decision_by_dedupe_key(self, dedupe_key: str) -> DecisionRecord | None:
        row = (
            self.session.execute(
                select(decision_records_table).where(
                    decision_records_table.c.dedupe_key == dedupe_key
                )
            )
            .mappings()
            .first()
        )
        return DecisionRecord(**dict(row)) if row is not None else None

    def create_decision(self, **values) -> DecisionRecord:  # type: ignore[no-untyped-def]
        row_id = new_id()
        self.session.execute(insert(decision_records_table).values(id=row_id, **values))
        return self.get_decision(row_id)

    def get_decision(self, decision_id: str) -> DecisionRecord:
        row = (
            self.session.execute(
                select(decision_records_table).where(decision_records_table.c.id == decision_id)
            )
            .mappings()
            .one()
        )
        return DecisionRecord(**dict(row))

    def find_dataset_by_key(self, dataset_key: str) -> EvaluationDatasetRecord | None:
        row = (
            self.session.execute(
                select(evaluation_datasets_table).where(
                    evaluation_datasets_table.c.dataset_key == dataset_key
                )
            )
            .mappings()
            .first()
        )
        return EvaluationDatasetRecord(**dict(row)) if row is not None else None

    def create_dataset(self, **values) -> EvaluationDatasetRecord:  # type: ignore[no-untyped-def]
        row_id = new_id()
        self.session.execute(insert(evaluation_datasets_table).values(id=row_id, **values))
        return self.get_dataset(row_id)

    def get_dataset(self, dataset_id: str) -> EvaluationDatasetRecord:
        row = (
            self.session.execute(
                select(evaluation_datasets_table).where(
                    evaluation_datasets_table.c.id == dataset_id
                )
            )
            .mappings()
            .one()
        )
        return EvaluationDatasetRecord(**dict(row))

    def find_case_by_dataset_feedback(
        self,
        *,
        evaluation_dataset_id: str,
        feedback_event_id: str,
    ) -> EvaluationCaseRecord | None:
        row = (
            self.session.execute(
                select(evaluation_cases_table).where(
                    evaluation_cases_table.c.evaluation_dataset_id == evaluation_dataset_id,
                    evaluation_cases_table.c.feedback_event_id == feedback_event_id,
                )
            )
            .mappings()
            .first()
        )
        return EvaluationCaseRecord(**dict(row)) if row is not None else None

    def create_case(self, **values) -> EvaluationCaseRecord:  # type: ignore[no-untyped-def]
        row_id = new_id()
        self.session.execute(insert(evaluation_cases_table).values(id=row_id, **values))
        return self.get_case(row_id)

    def get_case(self, case_id: str) -> EvaluationCaseRecord:
        row = (
            self.session.execute(
                select(evaluation_cases_table).where(evaluation_cases_table.c.id == case_id)
            )
            .mappings()
            .one()
        )
        return EvaluationCaseRecord(**dict(row))

    def create_run(self, **values) -> EvaluationRunRecord:  # type: ignore[no-untyped-def]
        row_id = new_id()
        self.session.execute(insert(evaluation_runs_table).values(id=row_id, **values))
        return self.get_run(row_id)

    def get_run(self, run_id: str) -> EvaluationRunRecord:
        row = (
            self.session.execute(
                select(evaluation_runs_table).where(evaluation_runs_table.c.id == run_id)
            )
            .mappings()
            .one()
        )
        return EvaluationRunRecord(**dict(row))

    def update_run(self, run_id: str, **values) -> EvaluationRunRecord:  # type: ignore[no-untyped-def]
        self.session.execute(
            update(evaluation_runs_table)
            .where(evaluation_runs_table.c.id == run_id)
            .values(**values)
        )
        return self.get_run(run_id)

    def find_result_by_run_case(
        self,
        *,
        evaluation_run_id: str,
        evaluation_case_id: str,
    ) -> EvaluationResultRecord | None:
        row = (
            self.session.execute(
                select(evaluation_results_table).where(
                    evaluation_results_table.c.evaluation_run_id == evaluation_run_id,
                    evaluation_results_table.c.evaluation_case_id == evaluation_case_id,
                )
            )
            .mappings()
            .first()
        )
        return EvaluationResultRecord(**dict(row)) if row is not None else None

    def create_result(self, **values) -> EvaluationResultRecord:  # type: ignore[no-untyped-def]
        row_id = new_id()
        self.session.execute(insert(evaluation_results_table).values(id=row_id, **values))
        return self.get_result(row_id)

    def get_result(self, result_id: str) -> EvaluationResultRecord:
        row = (
            self.session.execute(
                select(evaluation_results_table).where(evaluation_results_table.c.id == result_id)
            )
            .mappings()
            .one()
        )
        return EvaluationResultRecord(**dict(row))

    def create_quality_snapshot(
        self,
        **values,
    ) -> QualityMetricSnapshotRecord:  # type: ignore[no-untyped-def]
        row_id = new_id()
        self.session.execute(insert(quality_metric_snapshots_table).values(id=row_id, **values))
        row = (
            self.session.execute(
                select(quality_metric_snapshots_table).where(
                    quality_metric_snapshots_table.c.id == row_id
                )
            )
            .mappings()
            .one()
        )
        return QualityMetricSnapshotRecord(**dict(row))
