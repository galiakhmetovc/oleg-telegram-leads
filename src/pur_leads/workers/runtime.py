"""Runtime loop for scheduled worker jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Protocol, cast

from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.repositories.scheduler import SchedulerJobRecord
from pur_leads.services.audit import AuditService
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_sources import CatalogSourceService
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


def _checkpoint_after(handler_result: Any) -> Any:
    if isinstance(handler_result, JobHandlerResult):
        return handler_result.checkpoint_after
    if hasattr(handler_result, "checkpoint_after"):
        return {"message_id": handler_result.checkpoint_after}
    return None


def _result_summary(handler_result: Any) -> Any:
    if isinstance(handler_result, JobHandlerResult):
        return handler_result.result_summary
    if is_dataclass(handler_result):
        return asdict(cast(Any, handler_result))
    if isinstance(handler_result, dict):
        return handler_result
    if handler_result is None:
        return None
    return {"result": handler_result}
