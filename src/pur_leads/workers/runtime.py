"""Runtime loop for scheduled worker jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from typing import Any, Protocol, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.repositories.scheduler import SchedulerJobRecord
from pur_leads.models.telegram_sources import source_messages_table
from pur_leads.services.audit import AuditService
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.workers.message_context import MessageContextWorker
from pur_leads.workers.telegram_access import TelegramAccessWorker
from pur_leads.workers.telegram_polling import TelegramPollingWorker


JobHandler = Callable[[SchedulerJobRecord], Awaitable[Any]]


@dataclass(frozen=True)
class JobHandlerResult:
    result_summary: Any = None
    checkpoint_after: Any = None


@dataclass(frozen=True)
class WorkerRunResult:
    status: str
    job_id: str | None = None
    job_type: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ParsedArtifact:
    source_id: str
    artifact_id: str | None
    chunks: list[str]
    parser_name: str
    parser_version: str


@dataclass(frozen=True)
class CatalogExtractedFact:
    fact_type: str
    canonical_name: str
    value_json: Any
    confidence: float
    source_id: str | None
    chunk_id: str | None
    candidate_type: str
    proposed_action: str = "create"
    evidence_quote: str | None = None


@dataclass(frozen=True)
class LeadMessageForClassification:
    source_message_id: str
    monitored_source_id: str
    telegram_message_id: int
    sender_id: str | None
    message_date: Any
    message_text: str | None
    normalized_text: str | None


@dataclass(frozen=True)
class LeadClassifierMatch:
    match_type: str
    matched_text: str | None
    score: float
    classifier_snapshot_entry_id: str | None = None
    catalog_item_id: str | None = None
    catalog_term_id: str | None = None
    catalog_offer_id: str | None = None
    category_id: str | None = None


@dataclass(frozen=True)
class LeadClassifierResult:
    source_message_id: str
    classifier_version_id: str
    decision: str
    detection_mode: str
    confidence: float
    commercial_value_score: float | None = None
    negative_score: float | None = None
    high_value_signals_json: Any = None
    negative_signals_json: Any = None
    notify_reason: str | None = None
    reason: str | None = None
    matches: list[LeadClassifierMatch] | None = None


class ArtifactParserAdapter(Protocol):
    async def parse_artifact(
        self,
        *,
        source_id: str,
        artifact_id: str | None,
        payload: dict[str, Any],
    ) -> ParsedArtifact:
        """Parse one artifact/source into text chunks."""


class CatalogExtractorAdapter(Protocol):
    async def extract_catalog_facts(
        self,
        *,
        source_id: str | None,
        chunk_id: str | None,
        payload: dict[str, Any],
    ) -> list[CatalogExtractedFact]:
        """Extract catalog facts from a source/chunk scope."""


class LeadClassifierAdapter(Protocol):
    async def classify_message_batch(
        self,
        *,
        messages: list[LeadMessageForClassification],
        payload: dict[str, Any],
    ) -> list[LeadClassifierResult]:
        """Classify one batch of saved source messages into lead detection results."""


class WorkerRuntime:
    def __init__(
        self,
        session: Session,
        *,
        handlers: Mapping[str, JobHandler],
        worker_name: str = "worker",
        lease_seconds: int = 300,
    ) -> None:
        self.session = session
        self.handlers = handlers
        self.worker_name = worker_name
        self.lease_seconds = lease_seconds
        self.scheduler = SchedulerService(session)
        self.audit = AuditService(session)

    async def run_once(self) -> WorkerRunResult:
        job = self.scheduler.acquire_next(self.worker_name, lease_seconds=self.lease_seconds)
        if job is None:
            return WorkerRunResult(status="idle")

        handler = self.handlers.get(job.job_type)
        if handler is None:
            return self._fail_unsupported_job(job)

        try:
            handler_result = await handler(job)
        except Exception as exc:
            return self._fail_job(job, exc)

        self.scheduler.succeed(
            job.id,
            checkpoint_after=_checkpoint_after(handler_result),
            result_summary=_result_summary(handler_result),
        )
        return WorkerRunResult(status="succeeded", job_id=job.id, job_type=job.job_type)

    def _fail_unsupported_job(self, job: SchedulerJobRecord) -> WorkerRunResult:
        error = f"unsupported job type: {job.job_type}"
        self.audit.record_event(
            event_type="scheduler",
            severity="error",
            message=error,
            entity_type="scheduler_job",
            entity_id=job.id,
            details_json={
                "reason": "unsupported_job_type",
                "job_type": job.job_type,
                "scope_type": job.scope_type,
                "scope_id": job.scope_id,
            },
        )
        self.scheduler.fail_permanently(job.id, error=error)
        return WorkerRunResult(
            status="failed",
            job_id=job.id,
            job_type=job.job_type,
            message=error,
        )

    def _fail_job(self, job: SchedulerJobRecord, exc: Exception) -> WorkerRunResult:
        error = str(exc) or exc.__class__.__name__
        self.audit.record_event(
            event_type="scheduler",
            severity="error",
            message=error,
            entity_type="scheduler_job",
            entity_id=job.id,
            details_json={"reason": "handler_exception", "job_type": job.job_type},
        )
        self.scheduler.fail(job.id, error=error, retry_at=utc_now())
        return WorkerRunResult(
            status="failed",
            job_id=job.id,
            job_type=job.job_type,
            message=error,
        )


def build_telegram_handler_registry(
    session: Session,
    client: TelegramClientPort,
) -> dict[str, JobHandler]:
    access_worker = TelegramAccessWorker(session, client)
    polling_worker = TelegramPollingWorker(session, client)
    context_worker = MessageContextWorker(session, client)

    async def check_source_access(job: SchedulerJobRecord) -> JobHandlerResult:
        if job.monitored_source_id is None:
            raise ValueError("check_source_access requires monitored_source_id")
        result = await access_worker.check_source_access(
            job.monitored_source_id,
            userbot_account_id=job.userbot_account_id,
        )
        return JobHandlerResult(result_summary=asdict(result))

    async def fetch_source_preview(job: SchedulerJobRecord) -> JobHandlerResult:
        if job.monitored_source_id is None:
            raise ValueError("fetch_source_preview requires monitored_source_id")
        payload = job.payload_json or {}
        messages = await access_worker.fetch_preview(
            job.monitored_source_id,
            access_check_id=payload.get("access_check_id"),
            limit=payload.get("limit", 20),
        )
        return JobHandlerResult(result_summary={"preview_message_count": len(messages)})

    async def poll_monitored_source(job: SchedulerJobRecord) -> JobHandlerResult:
        if job.monitored_source_id is None:
            raise ValueError("poll_monitored_source requires monitored_source_id")
        payload = job.payload_json or {}
        result = await polling_worker.poll_monitored_source(
            job.monitored_source_id,
            scheduler_job_id=job.id,
            limit=payload.get("limit", 100),
        )
        return JobHandlerResult(
            checkpoint_after={"message_id": result.checkpoint_after},
            result_summary=asdict(result),
        )

    async def fetch_message_context(job: SchedulerJobRecord) -> JobHandlerResult:
        if job.source_message_id is None:
            raise ValueError("fetch_message_context requires source_message_id")
        payload = job.payload_json or {}
        result = await context_worker.fetch_context(
            job.source_message_id,
            before=payload.get("before", 2),
            after=payload.get("after", 2),
            reply_depth=payload.get("reply_depth", 2),
        )
        return JobHandlerResult(result_summary=asdict(result))

    return {
        "check_source_access": check_source_access,
        "fetch_source_preview": fetch_source_preview,
        "poll_monitored_source": poll_monitored_source,
        "fetch_message_context": fetch_message_context,
    }


def build_catalog_handler_registry(
    session: Session,
    *,
    parser: ArtifactParserAdapter | None = None,
    extractor: CatalogExtractorAdapter | None = None,
) -> dict[str, JobHandler]:
    source_service = CatalogSourceService(session)
    candidate_service = CatalogCandidateService(session)

    async def parse_artifact(job: SchedulerJobRecord) -> JobHandlerResult:
        if parser is None:
            raise ValueError("parse_artifact adapter is not configured")
        payload = job.payload_json or {}
        source_id = payload.get("source_id")
        if not isinstance(source_id, str):
            raise ValueError("parse_artifact requires payload.source_id")
        artifact_id = payload.get("artifact_id")
        if artifact_id is not None and not isinstance(artifact_id, str):
            raise ValueError("parse_artifact payload.artifact_id must be a string")
        parsed = await parser.parse_artifact(
            source_id=source_id,
            artifact_id=artifact_id,
            payload=payload,
        )
        chunks = source_service.replace_parsed_chunks(
            parsed.source_id,
            artifact_id=parsed.artifact_id,
            chunks=parsed.chunks,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
        )
        return JobHandlerResult(
            result_summary={"chunk_count": len(chunks), "parser_name": parsed.parser_name}
        )

    async def extract_catalog_facts(job: SchedulerJobRecord) -> JobHandlerResult:
        if extractor is None:
            raise ValueError("extract_catalog_facts adapter is not configured")
        payload = job.payload_json or {}
        source_id = payload.get("source_id")
        chunk_id = payload.get("chunk_id")
        if source_id is not None and not isinstance(source_id, str):
            raise ValueError("extract_catalog_facts payload.source_id must be a string")
        if chunk_id is not None and not isinstance(chunk_id, str):
            raise ValueError("extract_catalog_facts payload.chunk_id must be a string")
        facts = await extractor.extract_catalog_facts(
            source_id=source_id,
            chunk_id=chunk_id,
            payload=payload,
        )
        run = candidate_service.start_extraction_run(
            run_type="catalog_extraction",
            extractor_version=payload.get("extractor_version", "runtime-adapter"),
            model=payload.get("model"),
            prompt_version=payload.get("prompt_version"),
            source_scope_json={"source_id": source_id, "chunk_id": chunk_id},
        )
        candidate_count = 0
        for extracted in facts:
            fact = candidate_service.create_extracted_fact(
                extraction_run_id=run.id,
                fact_type=extracted.fact_type,
                canonical_name=extracted.canonical_name,
                value_json=extracted.value_json,
                confidence=extracted.confidence,
                source_id=extracted.source_id,
                chunk_id=extracted.chunk_id,
            )
            candidate_service.create_or_update_candidate_from_fact(
                fact.id,
                candidate_type=extracted.candidate_type,
                proposed_action=extracted.proposed_action,
                evidence_quote=extracted.evidence_quote,
                created_by="system",
            )
            candidate_count += 1
        candidate_service.finish_extraction_run(
            run.id,
            status="succeeded",
            stats_json={"fact_count": len(facts), "candidate_count": candidate_count},
        )
        return JobHandlerResult(
            result_summary={"fact_count": len(facts), "candidate_count": candidate_count}
        )

    return {"parse_artifact": parse_artifact, "extract_catalog_facts": extract_catalog_facts}


def build_lead_handler_registry(
    session: Session,
    *,
    classifier: LeadClassifierAdapter | None = None,
) -> dict[str, JobHandler]:
    lead_service = LeadService(session)

    async def classify_message_batch(job: SchedulerJobRecord) -> JobHandlerResult:
        if classifier is None:
            raise ValueError("classify_message_batch adapter is not configured")
        payload = job.payload_json or {}
        messages = _load_messages_for_classification(
            session,
            monitored_source_id=job.monitored_source_id,
            source_message_id=job.source_message_id,
            statuses=_classification_statuses(payload),
            limit=_positive_int(payload.get("limit"), default=50),
        )
        if not messages:
            return JobHandlerResult(
                result_summary={"message_count": 0, "event_count": 0, "cluster_count": 0}
            )

        results = await classifier.classify_message_batch(messages=messages, payload=payload)
        message_ids = {message.source_message_id for message in messages}
        _validate_classifier_results(message_ids, results)
        cluster_ids: set[str] = set()
        event_count = 0
        window_minutes = _positive_int(payload.get("cluster_window_minutes"), default=60)
        for result in results:
            if result.source_message_id not in message_ids:
                raise ValueError(
                    f"classifier returned unknown source_message_id: {result.source_message_id}"
                )
            event = lead_service.record_detection(
                source_message_id=result.source_message_id,
                classifier_version_id=result.classifier_version_id,
                result=LeadDetectionResult(
                    decision=result.decision,
                    detection_mode=result.detection_mode,
                    confidence=result.confidence,
                    commercial_value_score=result.commercial_value_score,
                    negative_score=result.negative_score,
                    high_value_signals_json=result.high_value_signals_json,
                    negative_signals_json=result.negative_signals_json,
                    notify_reason=result.notify_reason,
                    reason=result.reason,
                    matches=[
                        LeadMatchInput(
                            match_type=match.match_type,
                            matched_text=match.matched_text,
                            score=match.score,
                            classifier_snapshot_entry_id=match.classifier_snapshot_entry_id,
                            catalog_item_id=match.catalog_item_id,
                            catalog_term_id=match.catalog_term_id,
                            catalog_offer_id=match.catalog_offer_id,
                            category_id=match.category_id,
                        )
                        for match in result.matches or []
                    ],
                ),
            )
            event_count += 1
            if result.decision in {"lead", "maybe"}:
                cluster = lead_service.assign_event_to_cluster(
                    event.id,
                    window_minutes=window_minutes,
                )
                cluster_ids.add(cluster.id)
            _mark_message_classified(session, result.source_message_id)

        return JobHandlerResult(
            result_summary={
                "message_count": len(messages),
                "event_count": event_count,
                "cluster_count": len(cluster_ids),
            }
        )

    return {"classify_message_batch": classify_message_batch}


def _checkpoint_after(handler_result: Any) -> Any:
    if isinstance(handler_result, JobHandlerResult):
        return _json_ready(handler_result.checkpoint_after)
    if hasattr(handler_result, "checkpoint_after"):
        return {"message_id": handler_result.checkpoint_after}
    return None


def _result_summary(handler_result: Any) -> Any:
    if isinstance(handler_result, JobHandlerResult):
        return _json_ready(handler_result.result_summary)
    if is_dataclass(handler_result):
        return _json_ready(asdict(cast(Any, handler_result)))
    if isinstance(handler_result, dict):
        return _json_ready(handler_result)
    if handler_result is None:
        return None
    return {"result": handler_result}


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _load_messages_for_classification(
    session: Session,
    *,
    monitored_source_id: str | None,
    source_message_id: str | None,
    statuses: list[str],
    limit: int,
) -> list[LeadMessageForClassification]:
    query = select(source_messages_table).where(
        source_messages_table.c.classification_status.in_(statuses)
    )
    if source_message_id is not None:
        query = query.where(source_messages_table.c.id == source_message_id)
    elif monitored_source_id is not None:
        query = query.where(source_messages_table.c.monitored_source_id == monitored_source_id)
    rows = (
        session.execute(
            query.order_by(
                source_messages_table.c.message_date,
                source_messages_table.c.telegram_message_id,
            ).limit(limit)
        )
        .mappings()
        .all()
    )
    return [
        LeadMessageForClassification(
            source_message_id=row["id"],
            monitored_source_id=row["monitored_source_id"],
            telegram_message_id=row["telegram_message_id"],
            sender_id=row["sender_id"],
            message_date=row["message_date"],
            message_text=_source_message_text(dict(row)),
            normalized_text=row["normalized_text"],
        )
        for row in rows
    ]


def _classification_statuses(payload: dict[str, Any]) -> list[str]:
    configured = payload.get("classification_statuses")
    if isinstance(configured, list) and all(isinstance(value, str) for value in configured):
        return configured
    return ["queued", "unclassified"]


def _validate_classifier_results(
    message_ids: set[str],
    results: list[LeadClassifierResult],
) -> None:
    result_ids = [result.source_message_id for result in results]
    unique_result_ids = set(result_ids)
    unknown_ids = unique_result_ids - message_ids
    missing_ids = message_ids - unique_result_ids
    duplicate_ids = sorted(
        result_id for result_id in unique_result_ids if result_ids.count(result_id) > 1
    )
    if unknown_ids:
        raise ValueError(f"classifier returned unknown source_message_id: {sorted(unknown_ids)}")
    if missing_ids:
        raise ValueError(f"missing classifier results for source_message_id: {sorted(missing_ids)}")
    if duplicate_ids:
        raise ValueError(f"duplicate classifier results for source_message_id: {duplicate_ids}")


def _positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed <= 0:
        return default
    return parsed


def _mark_message_classified(session: Session, source_message_id: str) -> None:
    session.execute(
        update(source_messages_table)
        .where(source_messages_table.c.id == source_message_id)
        .values(classification_status="classified", updated_at=utc_now())
    )


def _source_message_text(row: dict[str, Any]) -> str | None:
    parts = [part for part in (row.get("text"), row.get("caption")) if part]
    return "\n".join(parts) if parts else None
