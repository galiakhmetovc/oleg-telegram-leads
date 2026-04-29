"""Runtime loop for scheduled worker jobs."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.integrations.catalog.external_page import FetchedExternalPage
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.integrations.telegram.types import ResolvedTelegramSource
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.repositories.scheduler import SchedulerJobRecord
from pur_leads.repositories.leads import LeadClusterRecord, LeadEventRecord
from pur_leads.repositories.telegram_sources import MonitoredSourceRecord, TelegramSourceRepository
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.services.audit import AuditService
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.classifier_snapshots import ClassifierSnapshotService
from pur_leads.services.evaluation import EvaluationService
from pur_leads.services.leads import LeadDetectionResult, LeadMatchInput, LeadService
from pur_leads.services.notifications import NotificationPolicyService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.settings import SettingsService
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


class ExternalPageFetcherAdapter(Protocol):
    async def fetch_page(self, *, url: str, payload: dict[str, Any]) -> FetchedExternalPage:
        """Fetch one external page into readable text."""


class LeadClassifierAdapter(Protocol):
    async def classify_message_batch(
        self,
        *,
        messages: list[LeadMessageForClassification],
        payload: dict[str, Any],
    ) -> list[LeadClassifierResult]:
        """Classify one batch of saved source messages into lead detection results."""


class LeadShadowClassifierAdapter(Protocol):
    model: str
    prompt_hash: str
    prompt_version: str
    last_token_usage_json: dict[str, Any] | None

    async def classify_message_batch(
        self,
        *,
        messages: list[LeadMessageForClassification],
        payload: dict[str, Any],
    ) -> list[LeadClassifierResult]:
        """Evaluate a batch in shadow mode without creating lead events."""


class LeadNotifierAdapter(Protocol):
    async def send_lead_notification(
        self,
        *,
        chat_id: str,
        text: str,
        message_thread_id: int | None = None,
    ) -> Any:
        """Send an urgent lead notification to an operator channel/chat."""


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
        now = utc_now()
        self.scheduler.recover_expired_leases(now)
        if "poll_monitored_source" in self.handlers:
            _enqueue_due_source_polls(self.session, self.scheduler, now)

        job = self.scheduler.acquire_next(
            self.worker_name,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        if job is None:
            return WorkerRunResult(status="idle")

        run_id = self.scheduler.start_run(job.id, worker_name=self.worker_name)
        handler = self.handlers.get(job.job_type)
        if handler is None:
            result = self._fail_unsupported_job(job)
            self.scheduler.finish_run(run_id, status="failed", error=result.message)
            return result

        try:
            handler_result = await handler(job)
        except Exception as exc:
            result = self._fail_job(job, exc)
            self.scheduler.finish_run(run_id, status="failed", error=result.message)
            return result

        checkpoint_after = _checkpoint_after(handler_result)
        result_summary = _result_summary(handler_result)
        self.scheduler.succeed(
            job.id,
            checkpoint_after=checkpoint_after,
            result_summary=result_summary,
        )
        self.scheduler.finish_run(run_id, status="succeeded", result_json=result_summary)
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
        error = _safe_exception_message(exc)
        retryable = getattr(exc, "retryable", None)
        if retryable is False:
            _mark_failed_notification_event(self.session, job=job, error=error)
            self.audit.record_event(
                event_type="scheduler",
                severity="error",
                message=error,
                entity_type="scheduler_job",
                entity_id=job.id,
                details_json={
                    "reason": "non_retryable_handler_exception",
                    "job_type": job.job_type,
                    "error_code": getattr(exc, "error_code", None),
                    "error_type": getattr(exc, "error_type", None),
                },
            )
            self.scheduler.fail_permanently(job.id, error=error)
            return WorkerRunResult(
                status="failed",
                job_id=job.id,
                job_type=job.job_type,
                message=error,
            )
        retry_at = _retry_at_for_exception(
            self.session,
            exc,
            attempt_number=job.attempt_count + 1,
        )
        _mark_failed_notification_event(self.session, job=job, error=error)
        self.audit.record_event(
            event_type="scheduler",
            severity="error",
            message=error,
            entity_type="scheduler_job",
            entity_id=job.id,
            details_json={"reason": "handler_exception", "job_type": job.job_type},
        )
        _delay_queued_peer_jobs_after_retry(self.session, job=job, retry_at=retry_at)
        self.scheduler.fail(job.id, error=error, retry_at=retry_at)
        return WorkerRunResult(
            status="failed",
            job_id=job.id,
            job_type=job.job_type,
            message=error,
        )


def build_telegram_handler_registry(
    session: Session,
    client: TelegramClientPort,
    *,
    artifact_storage_path: str | Path | None = None,
) -> dict[str, JobHandler]:
    access_worker = TelegramAccessWorker(session, client)
    polling_worker = TelegramPollingWorker(session, client)
    context_worker = MessageContextWorker(session, client)
    telegram_sources = TelegramSourceRepository(session)
    catalog_sources = CatalogSourceService(session)
    scheduler = SchedulerService(session)
    artifact_root = Path(artifact_storage_path or "./data/artifacts")

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

    async def download_artifact(job: SchedulerJobRecord) -> JobHandlerResult:
        if job.monitored_source_id is None:
            raise ValueError("download_artifact requires monitored_source_id")
        payload = job.payload_json or {}
        source_id = payload.get("source_id")
        telegram_message_id = payload.get("telegram_message_id")
        if not isinstance(source_id, str):
            raise ValueError("download_artifact requires payload.source_id")
        if not isinstance(telegram_message_id, int):
            raise ValueError("download_artifact requires payload.telegram_message_id")

        monitored_source = telegram_sources.get(job.monitored_source_id)
        if monitored_source is None:
            raise KeyError(job.monitored_source_id)
        downloaded = await client.download_message_document(
            _resolved_source_from_record(monitored_source),
            message_id=telegram_message_id,
            destination_dir=artifact_root
            / "telegram"
            / job.monitored_source_id
            / str(telegram_message_id),
        )
        sha256 = (
            _sha256_file(Path(downloaded.local_path))
            if downloaded.status == "downloaded" and downloaded.local_path is not None
            else None
        )
        artifact = catalog_sources.record_artifact(
            source_id,
            artifact_type="document",
            file_name=downloaded.file_name,
            mime_type=downloaded.mime_type,
            file_size=downloaded.file_size,
            sha256=sha256,
            local_path=downloaded.local_path,
            download_status=downloaded.status,
            skip_reason=downloaded.skip_reason,
        )
        if _should_parse_artifact(
            download_status=artifact.download_status,
            file_name=artifact.file_name,
            mime_type=artifact.mime_type,
        ):
            scheduler.enqueue(
                job_type="parse_artifact",
                scope_type="parser",
                scope_id=artifact.id,
                idempotency_key=f"parse-artifact:{artifact.id}",
                payload_json={
                    "source_id": artifact.source_id,
                    "artifact_id": artifact.id,
                    "local_path": artifact.local_path,
                    "file_name": artifact.file_name,
                    "mime_type": artifact.mime_type,
                },
            )
        return JobHandlerResult(
            result_summary={
                "download_status": artifact.download_status,
                "artifact_id": artifact.id,
                "file_name": artifact.file_name,
            }
        )

    return {
        "check_source_access": check_source_access,
        "fetch_source_preview": fetch_source_preview,
        "poll_monitored_source": poll_monitored_source,
        "fetch_message_context": fetch_message_context,
        "download_artifact": download_artifact,
    }


def build_catalog_handler_registry(
    session: Session,
    *,
    parser: ArtifactParserAdapter | None = None,
    extractor: CatalogExtractorAdapter | None = None,
    external_page_fetcher: ExternalPageFetcherAdapter | None = None,
) -> dict[str, JobHandler]:
    source_service = CatalogSourceService(session)
    candidate_service = CatalogCandidateService(session)
    scheduler = SchedulerService(session)

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
        for chunk in chunks:
            scheduler.enqueue(
                job_type="extract_catalog_facts",
                scope_type="parser",
                scope_id=chunk.id,
                idempotency_key=f"extract-catalog-facts:{chunk.id}",
                payload_json={
                    "source_id": chunk.source_id,
                    "artifact_id": chunk.artifact_id,
                    "chunk_id": chunk.id,
                    "extractor_version": "pur-heuristic-1",
                },
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
        run = candidate_service.start_extraction_run(
            run_type="catalog_extraction",
            extractor_version=_extractor_metadata(
                extractor, payload, "extractor_version", "runtime-adapter"
            ),
            model=_extractor_metadata(extractor, payload, "model", None),
            prompt_version=_extractor_metadata(extractor, payload, "prompt_version", None),
            source_scope_json={"source_id": source_id, "chunk_id": chunk_id},
        )
        try:
            facts = await extractor.extract_catalog_facts(
                source_id=source_id,
                chunk_id=chunk_id,
                payload=payload,
            )
        except Exception as exc:
            candidate_service.finish_extraction_run(
                run.id,
                status="failed",
                error=str(exc) or exc.__class__.__name__,
                token_usage_json=_extractor_token_usage(extractor),
            )
            raise
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
        if candidate_count:
            ClassifierSnapshotService(session).build_snapshot(
                created_by="system",
                model="builtin-fuzzy",
                settings_snapshot={
                    "trigger": "catalog_extraction",
                    "extraction_run_id": run.id,
                },
                notes="Automatically rebuilt after catalog extraction",
            )
        candidate_service.finish_extraction_run(
            run.id,
            status="succeeded",
            stats_json={"fact_count": len(facts), "candidate_count": candidate_count},
            token_usage_json=_extractor_token_usage(extractor),
        )
        return JobHandlerResult(
            result_summary={"fact_count": len(facts), "candidate_count": candidate_count}
        )

    async def fetch_external_page(job: SchedulerJobRecord) -> JobHandlerResult:
        if external_page_fetcher is None:
            raise ValueError("fetch_external_page adapter is not configured")
        payload = job.payload_json or {}
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("fetch_external_page requires payload.url")
        fetched = await external_page_fetcher.fetch_page(url=url.strip(), payload=payload)
        normalized_url = _normalize_external_url(fetched.final_url or fetched.url)
        source = source_service.upsert_source(
            source_type=_external_page_source_type(normalized_url),
            origin=_external_page_origin(normalized_url),
            external_id=normalized_url,
            url=normalized_url,
            title=fetched.title,
            fetched_at=utc_now(),
            raw_text=fetched.text,
            metadata_json={
                "requested_url": fetched.url,
                "final_url": fetched.final_url,
                "status_code": fetched.status_code,
                "content_type": fetched.content_type,
                "parent_source_id": payload.get("parent_source_id"),
                "source_message_id": payload.get("source_message_id"),
                "monitored_source_id": payload.get("monitored_source_id"),
            },
        )
        chunks = source_service.replace_parsed_chunks(
            source.id,
            chunks=_chunk_text(fetched.text),
            parser_name="external-page-text",
            parser_version="1",
        )
        for chunk in chunks:
            scheduler.enqueue(
                job_type="extract_catalog_facts",
                scope_type="parser",
                scope_id=chunk.id,
                idempotency_key=f"extract-catalog-facts:{chunk.id}",
                payload_json={
                    "source_id": chunk.source_id,
                    "chunk_id": chunk.id,
                    "extractor_version": "external-page-runtime",
                },
            )
        return JobHandlerResult(
            result_summary={
                "source_id": source.id,
                "chunk_count": len(chunks),
                "status_code": fetched.status_code,
            }
        )

    return {
        "parse_artifact": parse_artifact,
        "extract_catalog_facts": extract_catalog_facts,
        "fetch_external_page": fetch_external_page,
    }


def build_lead_handler_registry(
    session: Session,
    *,
    classifier: LeadClassifierAdapter | None = None,
    shadow_classifier: LeadShadowClassifierAdapter | None = None,
    notifier: LeadNotifierAdapter | None = None,
) -> dict[str, JobHandler]:
    lead_service = LeadService(session)
    evaluation_service = EvaluationService(session)
    notification_policy = NotificationPolicyService(session)
    scheduler = SchedulerService(session)
    settings = SettingsService(session)

    async def classify_message_batch(job: SchedulerJobRecord) -> JobHandlerResult:
        if classifier is None:
            raise ValueError("classify_message_batch adapter is not configured")
        return await _run_classification_job(
            job,
            default_statuses=["queued", "unclassified"],
            force_detection_mode=None,
            mark_messages_classified=True,
            notify_retro=False,
        )

    async def reclassify_messages(job: SchedulerJobRecord) -> JobHandlerResult:
        if classifier is None:
            raise ValueError("classify_message_batch adapter is not configured")
        job_payload = job.payload_json or {}
        return await _run_classification_job(
            job,
            default_statuses=["classified"],
            force_detection_mode="retro_research",
            mark_messages_classified=False,
            notify_retro=_truthy(job_payload.get("notify_retro")),
            chain_next_batch=_truthy(job_payload.get("chain_next_batch", True)),
        )

    async def _run_classification_job(
        job: SchedulerJobRecord,
        *,
        default_statuses: list[str],
        force_detection_mode: str | None,
        mark_messages_classified: bool,
        notify_retro: bool,
        chain_next_batch: bool = False,
    ) -> JobHandlerResult:
        if classifier is None:
            raise ValueError("classify_message_batch adapter is not configured")
        payload = dict(job.payload_json or {})
        if force_detection_mode is not None:
            payload.setdefault("classification_statuses", default_statuses)
            payload["detection_mode"] = force_detection_mode
        statuses = (
            _classification_statuses(payload)
            if "classification_statuses" in payload
            else default_statuses
        )
        limit = _positive_int(payload.get("limit"), default=50)
        cursor = _classification_cursor(payload)
        should_chain_next_batch = chain_next_batch and job.source_message_id is None
        loaded_messages = _load_messages_for_classification(
            session,
            monitored_source_id=job.monitored_source_id,
            source_message_id=job.source_message_id,
            statuses=statuses,
            cursor=cursor,
            limit=limit + 1 if should_chain_next_batch else limit,
        )
        messages = loaded_messages[:limit]
        has_next_batch = should_chain_next_batch and len(loaded_messages) > len(messages)
        if not messages:
            return JobHandlerResult(
                result_summary={"message_count": 0, "event_count": 0, "cluster_count": 0}
            )

        results = await classifier.classify_message_batch(messages=messages, payload=payload)
        if force_detection_mode is not None:
            results = [replace(result, detection_mode=force_detection_mode) for result in results]
        message_ids = {message.source_message_id for message in messages}
        _validate_classifier_results(message_ids, results)
        shadow_summary = await _run_shadow_classification(
            session,
            settings,
            evaluation_service,
            shadow_classifier=shadow_classifier,
            messages=messages,
            payload=payload,
        )
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
                _enqueue_context_fetch(
                    session,
                    scheduler,
                    source_message_id=result.source_message_id,
                )
                _enqueue_lead_notification(
                    scheduler,
                    settings,
                    notification_policy,
                    cluster=cluster,
                    event=event,
                    decision=result.decision,
                    confidence=result.confidence,
                    notify_reason=result.notify_reason,
                    notify_retro_requested=notify_retro,
                )
            if mark_messages_classified:
                _mark_message_classified(session, result.source_message_id)

        if has_next_batch:
            next_cursor = _message_classification_cursor(messages[-1])
            next_payload = dict(payload)
            next_payload["cursor"] = next_cursor
            next_payload["chain_next_batch"] = True
            _enqueue_next_reclassification_batch(
                scheduler,
                job=job,
                payload=next_payload,
                cursor=next_cursor,
            )

        result_summary = {
            "message_count": len(messages),
            "event_count": event_count,
            "cluster_count": len(cluster_ids),
        }
        if shadow_summary is not None:
            result_summary.update(shadow_summary)
        return JobHandlerResult(result_summary=result_summary)

    async def send_notifications(job: SchedulerJobRecord) -> JobHandlerResult:
        if notifier is None:
            raise ValueError("lead notifier adapter is not configured")
        payload = job.payload_json or {}
        chat_id = payload.get("chat_id")
        text = payload.get("text")
        cluster_id = payload.get("cluster_id")
        message_thread_id = payload.get("message_thread_id")
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise ValueError("send_notifications requires payload.chat_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("send_notifications requires payload.text")
        if not isinstance(cluster_id, str) or not cluster_id.strip():
            raise ValueError("send_notifications requires payload.cluster_id")
        notification_kwargs: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if isinstance(message_thread_id, int):
            notification_kwargs["message_thread_id"] = message_thread_id
        provider_result = await notifier.send_lead_notification(**notification_kwargs)
        notification_event_id = payload.get("notification_event_id")
        if isinstance(notification_event_id, str) and notification_event_id.strip():
            notification_policy.mark_sent(notification_event_id, provider_result)
        cluster = lead_service.mark_cluster_notified(cluster_id)
        return JobHandlerResult(
            result_summary={
                "cluster_id": cluster.id,
                "notify_update_count": cluster.notify_update_count,
                "provider_result": provider_result,
            }
        )

    return {
        "classify_message_batch": classify_message_batch,
        "reclassify_messages": reclassify_messages,
        "send_notifications": send_notifications,
    }


async def _run_shadow_classification(
    session: Session,
    settings: SettingsService,
    evaluation_service: EvaluationService,
    *,
    shadow_classifier: LeadShadowClassifierAdapter | None,
    messages: list[LeadMessageForClassification],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if shadow_classifier is None or not _lead_shadow_enabled(settings, payload):
        return None

    limit = _positive_int(
        payload.get(
            "lead_llm_shadow_max_messages_per_job",
            settings.get("lead_llm_shadow_max_messages_per_job"),
        ),
        default=10,
    )
    shadow_messages = messages[:limit]
    shadow_payload = dict(payload)
    shadow_payload["shadow_mode"] = True
    shadow_payload.setdefault("detection_mode", "live")
    try:
        shadow_results = await shadow_classifier.classify_message_batch(
            messages=shadow_messages,
            payload=shadow_payload,
        )
        _validate_classifier_results(
            {message.source_message_id for message in shadow_messages},
            shadow_results,
        )
    except Exception as exc:
        error = _safe_exception_message(exc)
        AuditService(session).record_event(
            event_type="ai_request",
            severity="warning",
            message=f"Lead LLM shadow classifier failed: {error}",
            entity_type="lead_detection_shadow",
            details_json={
                "reason": "shadow_classifier_failed",
                "error": error,
                "model": shadow_classifier.model,
                "prompt_version": shadow_classifier.prompt_version,
                "message_count": len(shadow_messages),
            },
        )
        if not _lead_shadow_fallback_on_error(settings, payload):
            raise
        return {"shadow_decision_count": 0, "shadow_error": error}

    message_by_id = {message.source_message_id: message for message in shadow_messages}
    for result in shadow_results:
        _record_shadow_decision(
            evaluation_service,
            shadow_classifier=shadow_classifier,
            message=message_by_id[result.source_message_id],
            result=result,
        )
    return {"shadow_decision_count": len(shadow_results)}


def _lead_shadow_enabled(settings: SettingsService, payload: dict[str, Any]) -> bool:
    if "lead_llm_shadow_enabled" in payload:
        return _truthy(payload["lead_llm_shadow_enabled"])
    return _truthy(settings.get("lead_llm_shadow_enabled"))


def _lead_shadow_fallback_on_error(settings: SettingsService, payload: dict[str, Any]) -> bool:
    if "lead_llm_shadow_fallback_on_error" in payload:
        return _truthy(payload["lead_llm_shadow_fallback_on_error"])
    configured = settings.get("lead_llm_shadow_fallback_on_error")
    return True if configured is None else _truthy(configured)


def _record_shadow_decision(
    evaluation_service: EvaluationService,
    *,
    shadow_classifier: LeadShadowClassifierAdapter,
    message: LeadMessageForClassification,
    result: LeadClassifierResult,
) -> None:
    evaluation_service.record_decision(
        decision_type="lead_detection_shadow",
        entity_type="source_message",
        entity_id=result.source_message_id,
        dedupe_key=_lead_shadow_dedupe_key(shadow_classifier, result),
        source_message_id=result.source_message_id,
        prompt_hash=shadow_classifier.prompt_hash,
        prompt_version=shadow_classifier.prompt_version,
        model=shadow_classifier.model,
        decision=result.decision,
        confidence=result.confidence,
        reason=result.reason,
        input_json={
            "message_text": message.message_text,
            "telegram_message_id": message.telegram_message_id,
            "sender_id": message.sender_id,
            "detection_mode": result.detection_mode,
            "shadow_mode": True,
        },
        evidence_json={
            "matches": [_shadow_decision_trace_match(match) for match in result.matches or []],
            "high_value_signals": result.high_value_signals_json,
            "negative_signals": result.negative_signals_json,
        },
        output_json={
            "commercial_value_score": result.commercial_value_score,
            "negative_score": result.negative_score,
            "notify_reason": result.notify_reason,
            "token_usage": shadow_classifier.last_token_usage_json,
        },
        created_by="llm-shadow",
    )


def _lead_shadow_dedupe_key(
    shadow_classifier: LeadShadowClassifierAdapter,
    result: LeadClassifierResult,
) -> str:
    material = {
        "source_message_id": result.source_message_id,
        "detection_mode": result.detection_mode,
        "model": shadow_classifier.model,
        "prompt_hash": shadow_classifier.prompt_hash,
        "prompt_version": shadow_classifier.prompt_version,
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:32]
    return f"lead_detection_shadow:{digest}"


def _shadow_decision_trace_match(match: LeadClassifierMatch) -> dict[str, Any]:
    return {
        "catalog_item_id": match.catalog_item_id,
        "catalog_term_id": match.catalog_term_id,
        "catalog_offer_id": match.catalog_offer_id,
        "category_id": match.category_id,
        "match_type": match.match_type,
        "matched_text": match.matched_text,
        "score": match.score,
    }


def _enqueue_due_source_polls(
    session: Session,
    scheduler: SchedulerService,
    now: datetime,
) -> None:
    rows = (
        session.execute(
            select(monitored_sources_table).where(
                monitored_sources_table.c.status == "active",
                monitored_sources_table.c.phase_enabled.is_(True),
                or_(
                    monitored_sources_table.c.next_poll_at.is_(None),
                    monitored_sources_table.c.next_poll_at <= _to_db_datetime(now),
                ),
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        source_id = row["id"]
        if _has_active_poll_job(session, source_id):
            continue
        scheduler.enqueue(
            job_type="poll_monitored_source",
            scope_type="telegram_source",
            scope_id=source_id,
            userbot_account_id=row["assigned_userbot_account_id"],
            monitored_source_id=source_id,
            idempotency_key=f"source:{source_id}:poll:active",
            run_after_at=now,
            checkpoint_before_json={"message_id": row["checkpoint_message_id"]},
            payload_json={"limit": 100, "scheduled_by": "worker_due_poll"},
        )


def _has_active_poll_job(session: Session, source_id: str) -> bool:
    row = (
        session.execute(
            select(scheduler_jobs_table.c.id).where(
                scheduler_jobs_table.c.job_type == "poll_monitored_source",
                scheduler_jobs_table.c.monitored_source_id == source_id,
                scheduler_jobs_table.c.status.in_(["queued", "running"]),
            )
        )
        .mappings()
        .first()
    )
    return row is not None


def _mark_failed_notification_event(
    session: Session,
    *,
    job: SchedulerJobRecord,
    error: str,
) -> None:
    if job.job_type != "send_notifications":
        return
    payload = job.payload_json or {}
    notification_event_id = payload.get("notification_event_id")
    if isinstance(notification_event_id, str) and notification_event_id.strip():
        NotificationPolicyService(session).mark_failed(notification_event_id, error)


def _enqueue_context_fetch(
    session: Session,
    scheduler: SchedulerService,
    *,
    source_message_id: str,
) -> None:
    scheduler.enqueue(
        job_type="fetch_message_context",
        scope_type="telegram_source",
        source_message_id=source_message_id,
        userbot_account_id=_message_userbot_account_id(session, source_message_id),
        idempotency_key=f"context:{source_message_id}",
        payload_json={"before": 2, "after": 2, "reply_depth": 2},
    )


def _enqueue_next_reclassification_batch(
    scheduler: SchedulerService,
    *,
    job: SchedulerJobRecord,
    payload: dict[str, Any],
    cursor: dict[str, Any],
) -> None:
    scope_key = job.monitored_source_id or job.scope_id or "global"
    material = _json_ready(
        {
            "scope_key": scope_key,
            "trigger_reason": payload.get("trigger_reason"),
            "classification_statuses": payload.get("classification_statuses"),
            "detection_mode": payload.get("detection_mode"),
            "cursor": cursor,
        }
    )
    digest = hashlib.sha256(str(material).encode("utf-8")).hexdigest()[:16]
    scheduler.enqueue(
        job_type="reclassify_messages",
        scope_type=job.scope_type,
        priority=job.priority,
        scope_id=job.scope_id,
        userbot_account_id=job.userbot_account_id,
        monitored_source_id=job.monitored_source_id,
        idempotency_key=f"retro-reclassify:{scope_key}:{cursor['source_message_id']}:{digest}",
        payload_json=payload,
    )


def _enqueue_lead_notification(
    scheduler: SchedulerService,
    settings: SettingsService,
    notification_policy: NotificationPolicyService,
    *,
    cluster: LeadClusterRecord,
    event: LeadEventRecord,
    decision: str,
    confidence: float,
    notify_reason: str | None,
    notify_retro_requested: bool,
) -> None:
    chat_id = settings.get("telegram_lead_notification_chat_id")
    stripped_chat_id = chat_id.strip() if isinstance(chat_id, str) else None
    message_thread_id = settings.get("telegram_lead_notification_thread_id")
    text = _lead_notification_text(
        decision=decision,
        confidence=confidence,
        message_text=event.message_text,
        notify_reason=notify_reason,
        reason=event.reason,
        message_url=event.message_url,
    )
    policy_decision = notification_policy.evaluate_lead_event(
        settings=settings,
        cluster=cluster,
        event=event,
        notify_retro_requested=notify_retro_requested,
    )
    payload_json = {
        "cluster_id": cluster.id,
        "lead_event_id": event.id,
        "decision": decision,
        "confidence": confidence,
        "message_url": event.message_url,
        "text": text if policy_decision.should_enqueue else None,
    }
    notification_event_id = notification_policy.record_lead_policy_event(
        decision=policy_decision,
        cluster=cluster,
        event=event,
        target_ref=stripped_chat_id,
        payload_json=payload_json,
    )
    if not policy_decision.should_enqueue or not stripped_chat_id:
        return
    job = scheduler.enqueue(
        job_type="send_notifications",
        scope_type="global",
        scope_id=cluster.id,
        monitored_source_id=event.monitored_source_id,
        source_message_id=event.source_message_id,
        idempotency_key=policy_decision.dedupe_key,
        priority="high",
        payload_json={
            "cluster_id": cluster.id,
            "lead_event_id": event.id,
            "notification_event_id": notification_event_id,
            "chat_id": stripped_chat_id,
            "text": text,
            "message_thread_id": message_thread_id if isinstance(message_thread_id, int) else None,
        },
    )
    notification_policy.mark_queued_job(notification_event_id, job.id)


def _lead_notification_text(
    *,
    decision: str,
    confidence: float,
    message_text: str | None,
    notify_reason: str | None,
    reason: str | None,
    message_url: str | None,
) -> str:
    lines = [
        f"Новый лид: {decision} ({round(confidence * 100)}%)",
        message_text or "(без текста)",
        f"Причина: {notify_reason or reason or 'требуется проверка'}",
    ]
    if message_url:
        lines.append(f"Источник: {message_url}")
    return "\n".join(lines)


def _message_userbot_account_id(session: Session, source_message_id: str) -> str | None:
    row = (
        session.execute(
            select(monitored_sources_table.c.assigned_userbot_account_id)
            .select_from(
                source_messages_table.join(
                    monitored_sources_table,
                    source_messages_table.c.monitored_source_id == monitored_sources_table.c.id,
                )
            )
            .where(source_messages_table.c.id == source_message_id)
        )
        .mappings()
        .first()
    )
    return row["assigned_userbot_account_id"] if row is not None else None


def _to_db_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _checkpoint_after(handler_result: Any) -> Any:
    if isinstance(handler_result, JobHandlerResult):
        return _json_ready(handler_result.checkpoint_after)
    if hasattr(handler_result, "checkpoint_after"):
        return {"message_id": handler_result.checkpoint_after}
    return None


def _extractor_metadata(
    extractor: CatalogExtractorAdapter,
    payload: dict[str, Any],
    key: str,
    default: Any,
) -> Any:
    value = getattr(extractor, key, None)
    if value is not None:
        return value
    return payload.get(key, default)


def _extractor_token_usage(extractor: CatalogExtractorAdapter) -> Any:
    return getattr(extractor, "last_token_usage_json", None)


def _normalize_external_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("external page URL must be absolute http(s)")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.query,
            "",
        )
    )


def _external_page_source_type(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return "telegraph_page" if host == "telegra.ph" else "external_page"


def _external_page_origin(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _chunk_text(text: str, *, max_chars: int = 6000) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for paragraph in normalized.splitlines() or [normalized]:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and current_size + len(paragraph) + 1 > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_size = 0
        current.append(paragraph)
        current_size += len(paragraph) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks or [normalized[:max_chars]]


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
    cursor: dict[str, Any] | None,
    limit: int,
) -> list[LeadMessageForClassification]:
    query = select(source_messages_table).where(
        source_messages_table.c.classification_status.in_(statuses)
    )
    if source_message_id is not None:
        query = query.where(source_messages_table.c.id == source_message_id)
    elif monitored_source_id is not None:
        query = query.where(source_messages_table.c.monitored_source_id == monitored_source_id)
    if source_message_id is None and cursor is not None:
        cursor_date = _to_db_datetime(_classification_cursor_datetime(cursor["message_date"]))
        cursor_message_id = _classification_cursor_int(cursor["telegram_message_id"])
        cursor_source_message_id = cursor["source_message_id"]
        query = query.where(
            or_(
                source_messages_table.c.message_date > cursor_date,
                and_(
                    source_messages_table.c.message_date == cursor_date,
                    source_messages_table.c.telegram_message_id > cursor_message_id,
                ),
                and_(
                    source_messages_table.c.message_date == cursor_date,
                    source_messages_table.c.telegram_message_id == cursor_message_id,
                    source_messages_table.c.id > cursor_source_message_id,
                ),
            )
        )
    rows = (
        session.execute(
            query.order_by(
                source_messages_table.c.message_date,
                source_messages_table.c.telegram_message_id,
                source_messages_table.c.id,
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


def _classification_cursor(payload: dict[str, Any]) -> dict[str, Any] | None:
    configured = payload.get("cursor")
    if configured is None:
        return None
    if not isinstance(configured, dict):
        raise ValueError("classification cursor must be an object")
    required_keys = {"message_date", "telegram_message_id", "source_message_id"}
    missing_keys = required_keys - set(configured)
    if missing_keys:
        raise ValueError(f"classification cursor is missing keys: {sorted(missing_keys)}")
    source_message_id = configured["source_message_id"]
    if not isinstance(source_message_id, str) or not source_message_id.strip():
        raise ValueError("classification cursor.source_message_id must be a non-empty string")
    return {
        "message_date": _classification_cursor_datetime(configured["message_date"]),
        "telegram_message_id": _classification_cursor_int(configured["telegram_message_id"]),
        "source_message_id": source_message_id,
    }


def _classification_cursor_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("classification cursor.message_date must be an ISO datetime") from exc
    raise ValueError("classification cursor.message_date must be a datetime")


def _classification_cursor_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("classification cursor.telegram_message_id must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("classification cursor.telegram_message_id must be an integer") from exc


def _message_classification_cursor(message: LeadMessageForClassification) -> dict[str, Any]:
    return {
        "message_date": _json_ready(message.message_date),
        "telegram_message_id": message.telegram_message_id,
        "source_message_id": message.source_message_id,
    }


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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _safe_exception_message(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _retry_at_for_exception(
    session: Session,
    exc: Exception,
    *,
    attempt_number: int,
) -> datetime:
    retry_after_seconds = getattr(exc, "retry_after_seconds", None)
    if isinstance(retry_after_seconds, int | float) and retry_after_seconds > 0:
        base_delay = float(retry_after_seconds)
    else:
        base_delay = _float_setting(session, "worker_retry_base_delay_seconds", 5.0)
    multiplier = max(1.0, _float_setting(session, "worker_retry_backoff_multiplier", 2.0))
    max_delay = max(1.0, _float_setting(session, "worker_retry_max_delay_seconds", 900.0))
    exponent = max(0, attempt_number - 1)
    delay_seconds = min(max_delay, base_delay * (multiplier**exponent))
    if not (isinstance(retry_after_seconds, int | float) and retry_after_seconds > 0):
        delay_seconds = _jitter_delay(
            delay_seconds,
            mode=str(SettingsService(session).get("worker_retry_jitter_mode") or "full"),
        )
    return utc_now() + timedelta(seconds=int(delay_seconds))


def _jitter_delay(delay_seconds: float, *, mode: str) -> float:
    bounded = max(1.0, delay_seconds)
    normalized = mode.strip().casefold()
    if normalized == "none":
        return bounded
    if normalized == "equal":
        return bounded / 2 + random.uniform(0, bounded / 2)
    return random.uniform(1.0, bounded)


def _float_setting(session: Session, key: str, default: float) -> float:
    try:
        value = SettingsService(session).get(key)
    except Exception:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _delay_queued_peer_jobs_after_retry(
    session: Session,
    *,
    job: SchedulerJobRecord,
    retry_at: datetime,
) -> None:
    if job.job_type != "send_notifications":
        return
    if retry_at <= utc_now():
        return
    rows = (
        session.execute(
            select(scheduler_jobs_table.c.id)
            .where(
                scheduler_jobs_table.c.job_type == job.job_type,
                scheduler_jobs_table.c.status == "queued",
                scheduler_jobs_table.c.id != job.id,
                scheduler_jobs_table.c.run_after_at < _to_db_datetime(retry_at),
            )
            .order_by(scheduler_jobs_table.c.created_at)
        )
        .mappings()
        .all()
    )
    now = utc_now()
    for index, row in enumerate(rows):
        scheduled_at = retry_at + timedelta(seconds=index + 1)
        session.execute(
            update(scheduler_jobs_table)
            .where(scheduler_jobs_table.c.id == row["id"])
            .values(
                run_after_at=_to_db_datetime(scheduled_at),
                next_retry_at=_to_db_datetime(scheduled_at),
                updated_at=_to_db_datetime(now),
            )
        )


def _mark_message_classified(session: Session, source_message_id: str) -> None:
    session.execute(
        update(source_messages_table)
        .where(source_messages_table.c.id == source_message_id)
        .values(classification_status="classified", updated_at=utc_now())
    )


def _resolved_source_from_record(source: MonitoredSourceRecord) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=source.input_ref,
        source_kind=source.source_kind,
        telegram_id=source.telegram_id,
        username=source.username,
        title=source.title,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_parse_artifact(
    *,
    download_status: str,
    file_name: str | None,
    mime_type: str | None,
) -> bool:
    if download_status != "downloaded":
        return False
    if mime_type == "application/pdf":
        return True
    return file_name is not None and file_name.casefold().endswith(".pdf")


def _source_message_text(row: dict[str, Any]) -> str | None:
    parts = [part for part in (row.get("text"), row.get("caption")) if part]
    return "\n".join(parts) if parts else None
