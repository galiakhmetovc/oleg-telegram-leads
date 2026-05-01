"""Catalog candidate review routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import desc, insert, or_, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.models.catalog import classifier_examples_table, classifier_versions_table
from pur_leads.models.telegram_sources import monitored_sources_table, source_messages_table
from pur_leads.repositories.catalog_candidates import CatalogCandidateRecord
from pur_leads.services.catalog_candidates import CatalogCandidateService
from pur_leads.services.catalog_editor import CatalogEditorService
from pur_leads.services.catalog_raw_ingest import CatalogRawIngestService
from pur_leads.services.catalog_sources import CatalogSourceService
from pur_leads.services.classifier_snapshots import ClassifierSnapshotService
from pur_leads.services.evaluation import EvaluationService
from pur_leads.services.scheduler import SchedulerService
from pur_leads.services.settings import SettingsService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api/catalog")

CATALOG_MANUAL_INPUT_TYPES = {
    "catalog_note",
    "catalog_item",
    "catalog_term",
    "catalog_offer",
    "catalog_relation",
    "catalog_attribute",
}
EXAMPLE_INPUT_TYPES = {
    "lead_example": ("lead_positive", "positive", "lead"),
    "non_lead_example": ("lead_negative", "negative", "not_lead"),
    "maybe_example": ("maybe", "neutral", "maybe"),
}
ALLOWED_MANUAL_INPUT_TYPES = {
    "telegram_link",
    "manual_text",
    *CATALOG_MANUAL_INPUT_TYPES,
    *EXAMPLE_INPUT_TYPES.keys(),
}


class CandidateReviewRequest(BaseModel):
    action: str
    reason: str | None = None


class CandidateUpdateRequest(BaseModel):
    canonical_name: str | None = None
    normalized_value: dict[str, Any] | None = None
    reason: str | None = None


class CatalogTermInput(BaseModel):
    term: str
    term_type: str = "alias"
    language: str = "ru"
    weight: float = 1.0


class CatalogOfferInput(BaseModel):
    title: str
    offer_type: str = "price"
    description: str | None = None
    price_amount: float | None = None
    currency: str | None = None
    price_text: str | None = None
    terms_json: Any = None
    ttl_days: int | None = None
    ttl_source: str = "manual"


class CatalogEvidenceInput(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None
    quote: str | None = None
    source_text: str | None = None
    source_url: str | None = None
    source_id: str | None = None
    chunk_id: str | None = None
    artifact_id: str | None = None
    page_number: int | None = None
    location_json: dict[str, Any] | None = None
    evidence_type: str = "manual_note"
    confidence: float | None = None


class CatalogItemCreateRequest(BaseModel):
    name: str
    item_type: str = "product"
    category_slug: str | None = None
    description: str | None = None
    terms: list[CatalogTermInput] | None = None
    offers: list[CatalogOfferInput] | None = None
    evidence: CatalogEvidenceInput | None = None


class CatalogItemUpdateRequest(BaseModel):
    name: str | None = None
    item_type: str | None = None
    category_slug: str | None = None
    description: str | None = None
    status: str | None = None
    reason: str | None = None


class CatalogSnapshotRebuildRequest(BaseModel):
    reason: str | None = None


class ManualInputRequest(BaseModel):
    input_type: str
    text: str | None = None
    url: str | None = None
    chat_ref: str | None = None
    message_id: int | None = None
    evidence_note: str | None = None
    metadata_json: dict[str, Any] | None = None
    auto_extract: bool = False


@router.get("/items")
def list_catalog_items(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    items = CatalogEditorService(session).list_items(status=status, limit=limit)
    return {"items": [_item_payload(item) for item in items]}


@router.post("/items")
def create_catalog_item(
    payload: CatalogItemCreateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = CatalogEditorService(session)
    try:
        item = service.create_item(
            actor=_actor(validated),
            name=payload.name,
            item_type=payload.item_type,
            category_slug=payload.category_slug,
            description=payload.description,
            terms=[term.model_dump() for term in payload.terms or []],
            offers=[offer.model_dump() for offer in payload.offers or []],
            evidence=payload.evidence.model_dump() if payload.evidence else None,
        )
        detail = service.get_item_detail(item.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _manual_item_detail_payload(detail)


@router.get("/items/{item_id}")
def get_catalog_item(
    item_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = CatalogEditorService(session).get_item_detail(item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog item not found") from exc
    return _manual_item_detail_payload(detail)


@router.patch("/items/{item_id}")
def update_catalog_item(
    item_id: str,
    payload: CatalogItemUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = CatalogEditorService(session)
    try:
        service.update_item(
            item_id,
            actor=_actor(validated),
            name=payload.name,
            item_type=payload.item_type,
            category_slug=payload.category_slug,
            description=payload.description,
            status=payload.status,
        )
        detail = service.get_item_detail(item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog item not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _manual_item_detail_payload(detail)


@router.delete("/items/{item_id}")
def archive_catalog_item(
    item_id: str,
    payload: CatalogSnapshotRebuildRequest | None = None,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        item = CatalogEditorService(session).archive_item(
            item_id,
            actor=_actor(validated),
            reason=payload.reason if payload else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog item not found") from exc
    return {"item": _item_payload(item)}


@router.post("/items/{item_id}/terms")
def create_catalog_term(
    item_id: str,
    payload: CatalogTermInput,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        term = CatalogEditorService(session).add_term(
            item_id,
            actor=_actor(validated),
            term=payload.term,
            term_type=payload.term_type,
            language=payload.language,
            weight=payload.weight,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog item not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"term": _term_payload(term)}


@router.patch("/terms/{term_id}")
def update_catalog_term(
    term_id: str,
    payload: CatalogTermInput,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        term = CatalogEditorService(session).update_term(
            term_id,
            actor=_actor(validated),
            term=payload.term,
            term_type=payload.term_type,
            weight=payload.weight,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog term not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"term": _term_payload(term)}


@router.delete("/terms/{term_id}")
def archive_catalog_term(
    term_id: str,
    payload: CatalogSnapshotRebuildRequest | None = None,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        term = CatalogEditorService(session).archive_term(
            term_id,
            actor=_actor(validated),
            reason=payload.reason if payload else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog term not found") from exc
    return {"term": _term_payload(term)}


@router.post("/items/{item_id}/offers")
def create_catalog_offer(
    item_id: str,
    payload: CatalogOfferInput,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        offer = CatalogEditorService(session).add_offer(
            item_id,
            actor=_actor(validated),
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog item not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"offer": _offer_payload(offer)}


@router.patch("/offers/{offer_id}")
def update_catalog_offer(
    offer_id: str,
    payload: CatalogOfferInput,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        offer = CatalogEditorService(session).update_offer(
            offer_id,
            actor=_actor(validated),
            title=payload.title,
            price_text=payload.price_text,
            description=payload.description,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog offer not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"offer": _offer_payload(offer)}


@router.delete("/offers/{offer_id}")
def archive_catalog_offer(
    offer_id: str,
    payload: CatalogSnapshotRebuildRequest | None = None,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        offer = CatalogEditorService(session).archive_offer(
            offer_id,
            actor=_actor(validated),
            reason=payload.reason if payload else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Catalog offer not found") from exc
    return {"offer": _offer_payload(offer)}


@router.post("/snapshots/rebuild")
def rebuild_catalog_snapshot(
    payload: CatalogSnapshotRebuildRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    snapshot = CatalogEditorService(session).rebuild_classifier_snapshot(
        actor=_actor(validated),
        reason=payload.reason,
    )
    return {"classifier_snapshot": jsonable_encoder(asdict(snapshot))}


@router.get("/snapshots/latest")
def latest_catalog_snapshot(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = (
        session.execute(
            select(classifier_versions_table).order_by(desc(classifier_versions_table.c.version))
        )
        .mappings()
        .first()
    )
    return {"classifier_snapshot": jsonable_encoder(dict(row)) if row is not None else None}


@router.get("/raw-ingest")
def list_raw_ingest(
    source_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    payload = CatalogRawIngestService(session).list_overview(source_id=source_id, limit=limit)
    return jsonable_encoder(payload)


@router.get("/raw-ingest/messages/{source_message_id}")
def get_raw_ingest_message(
    source_message_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        payload = CatalogRawIngestService(session).get_message_detail(source_message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source message not found") from exc
    return jsonable_encoder(payload)


@router.get("/candidates")
def list_candidates(
    status: str | None = None,
    candidate_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    candidates = CatalogCandidateService(session).list_candidates(
        status=status,
        candidate_type=candidate_type,
        limit=limit,
    )
    return {"items": [_candidate_payload(candidate) for candidate in candidates]}


@router.get("/candidates/{candidate_id}")
def get_candidate_detail(
    candidate_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = CatalogCandidateService(session).get_candidate_detail(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    return _candidate_detail_payload(detail)


@router.patch("/candidates/{candidate_id}")
def update_candidate(
    candidate_id: str,
    payload: CandidateUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = CatalogCandidateService(session)
    try:
        service.update_candidate(
            candidate_id,
            actor=_actor(validated),
            canonical_name=payload.canonical_name,
            normalized_value=payload.normalized_value,
            reason=payload.reason,
        )
        detail = service.get_candidate_detail(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _candidate_detail_payload(detail)


@router.post("/candidates/{candidate_id}/review")
def review_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        result = CatalogCandidateService(session).review_candidate(
            candidate_id,
            action=payload.action,
            actor=_actor(validated),
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "candidate": _candidate_payload(result.candidate),
        "promotion": jsonable_encoder(asdict(result.promotion)) if result.promotion else None,
    }


@router.post("/manual-inputs")
def create_manual_input(
    payload: ManualInputRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if not bool(SettingsService(session).get("manual_catalog_add_enabled")):
        raise HTTPException(status_code=400, detail="Manual catalog additions are disabled")
    if payload.input_type not in ALLOWED_MANUAL_INPUT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported manual input_type")

    actor = _actor(validated)
    text = _clean_str(payload.text)
    url = _clean_str(payload.url)
    chat_ref = _clean_str(payload.chat_ref)
    message_id = payload.message_id
    if url:
        parsed_link = _parse_telegram_message_url(url)
        if parsed_link is not None:
            chat_ref = chat_ref or parsed_link["chat_ref"]
            message_id = message_id or parsed_link["message_id"]
    if text is None and url is None:
        raise HTTPException(status_code=400, detail="Manual input requires text or url")
    if _requires_evidence_note(session, payload.input_type) and not _clean_str(
        payload.evidence_note
    ):
        raise HTTPException(status_code=400, detail="evidence_note is required")

    metadata_json = dict(payload.metadata_json or {})
    metadata_json["input_type"] = payload.input_type
    result = CatalogSourceService(session).submit_manual_input(
        input_type=payload.input_type,
        submitted_by=actor,
        text=text,
        url=url,
        chat_ref=chat_ref,
        message_id=message_id,
        evidence_note=_clean_str(payload.evidence_note),
        metadata_json=metadata_json,
    )

    queued_jobs = []
    if (
        result.source is not None
        and text is not None
        and payload.auto_extract
        and payload.input_type in CATALOG_MANUAL_INPUT_TYPES | {"manual_text"}
        and bool(SettingsService(session).get("manual_catalog_create_candidate_first"))
    ):
        chunk = CatalogSourceService(session).replace_parsed_chunks(
            result.source.id,
            chunks=[text],
            parser_name="manual-input",
            parser_version="1",
        )[0]
        job = SchedulerService(session).enqueue(
            job_type="extract_catalog_facts",
            scope_type="parser",
            scope_id=chunk.id,
            priority="low",
            idempotency_key=f"manual-extract:{result.manual_input.id}:{chunk.id}",
            payload_json={
                "source_id": chunk.source_id,
                "chunk_id": chunk.id,
                "manual_input_id": result.manual_input.id,
                "extractor_version": "manual-input",
                "trigger": "manual_input",
            },
        )
        queued_jobs.append(job)

    classifier_example = None
    classifier_snapshot = None
    evaluation_case = None
    if payload.input_type in EXAMPLE_INPUT_TYPES:
        source_message = _find_source_message_by_link(
            session,
            chat_ref=chat_ref,
            message_id=message_id,
        )
        example_text = text or _source_message_text(source_message)
        if example_text is None:
            raise HTTPException(status_code=400, detail="Manual example requires readable text")
        classifier_example = _create_classifier_example(
            session,
            input_type=payload.input_type,
            example_text=example_text,
            actor=actor,
            raw_source_id=result.source.id if result.source is not None else None,
            source_message_id=source_message["id"] if source_message is not None else None,
            manual_input_id=result.manual_input.id,
            evidence_note=_clean_str(payload.evidence_note),
        )
        evaluation_case = EvaluationService(session).create_manual_lead_case(
            expected_decision=EXAMPLE_INPUT_TYPES[payload.input_type][2],
            message_text=example_text,
            actor=actor,
            manual_input_id=result.manual_input.id,
            classifier_example_id=classifier_example["id"],
            source_id=result.source.id if result.source is not None else None,
            source_message_id=source_message["id"] if source_message is not None else None,
            evidence_note=_clean_str(payload.evidence_note),
            input_type=payload.input_type,
            url=url,
        )
        classifier_snapshot = ClassifierSnapshotService(session).build_snapshot(
            created_by=actor,
            model="builtin-fuzzy",
            settings_snapshot={
                "trigger": "manual_input",
                "manual_input_id": result.manual_input.id,
                "classifier_example_id": classifier_example["id"],
            },
            notes="Automatically rebuilt after manual classifier example",
        )

    return {
        "manual_input": jsonable_encoder(asdict(result.manual_input)),
        "source": jsonable_encoder(asdict(result.source)) if result.source is not None else None,
        "queued_jobs": [jsonable_encoder(asdict(job)) for job in queued_jobs],
        "classifier_example": jsonable_encoder(classifier_example),
        "evaluation_case": jsonable_encoder(asdict(evaluation_case))
        if evaluation_case is not None
        else None,
        "classifier_snapshot": jsonable_encoder(asdict(classifier_snapshot))
        if classifier_snapshot is not None
        else None,
    }


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _candidate_payload(candidate: CatalogCandidateRecord) -> dict[str, Any]:
    payload = jsonable_encoder(asdict(candidate))
    payload["normalized_value"] = payload.pop("normalized_value_json")
    return payload


def _item_payload(item: Any) -> dict[str, Any]:
    return jsonable_encoder(asdict(item))


def _term_payload(term: Any) -> dict[str, Any]:
    return jsonable_encoder(asdict(term))


def _offer_payload(offer: Any) -> dict[str, Any]:
    return jsonable_encoder(asdict(offer))


def _manual_item_detail_payload(detail: Any) -> dict[str, Any]:
    return {
        "item": _item_payload(detail.item),
        "terms": [_term_payload(term) for term in detail.terms],
        "offers": [_offer_payload(offer) for offer in detail.offers],
        "attributes": jsonable_encoder(detail.attributes),
        "evidence": jsonable_encoder(detail.evidence),
    }


def _candidate_detail_payload(detail: Any) -> dict[str, Any]:
    return {
        "candidate": _candidate_payload(detail.candidate),
        "evidence": [_evidence_payload(row) for row in detail.evidence],
    }


def _evidence_payload(row: dict[str, Any]) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row["evidence_id"],
            "source_id": row["evidence_source_id"],
            "artifact_id": row["artifact_id"] or row["evidence_artifact_id"],
            "chunk_id": row["evidence_chunk_id"],
            "quote": row["quote"],
            "page_number": row["page_number"],
            "location": row["location_json"],
            "extractor_version": row["extractor_version"],
            "evidence_type": row["evidence_type"],
            "confidence": row["evidence_confidence"],
            "created_by": row["evidence_created_by"],
            "created_at": row["evidence_created_at"],
            "source": _source_payload(row),
            "artifact": _artifact_payload(row),
            "chunk": _chunk_payload(row),
        }
    )


def _source_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["source_id"] is None:
        return None
    return {
        "id": row["source_id"],
        "source_type": row["source_type"],
        "origin": row["source_origin"],
        "external_id": row["source_external_id"],
        "url": row["source_url"],
        "title": row["source_title"],
        "published_at": row["source_published_at"],
        "raw_text_excerpt": _excerpt(row["source_raw_text"]),
    }


def _artifact_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["artifact_id"] is None:
        return None
    return {
        "id": row["artifact_id"],
        "file_name": row["artifact_file_name"],
        "mime_type": row["artifact_mime_type"],
        "file_size": row["artifact_file_size"],
        "download_status": row["artifact_download_status"],
    }


def _chunk_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["chunk_id"] is None:
        return None
    return {
        "id": row["chunk_id"],
        "chunk_index": row["chunk_index"],
        "text": row["chunk_text"],
        "parser_name": row["chunk_parser_name"],
        "parser_version": row["chunk_parser_version"],
    }


def _excerpt(value: str | None, *, limit: int = 700) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _requires_evidence_note(session: Session, input_type: str) -> bool:
    if input_type not in CATALOG_MANUAL_INPUT_TYPES:
        return False
    return bool(SettingsService(session).get("manual_catalog_requires_evidence_note"))


def _parse_telegram_message_url(url: str) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if parsed.netloc not in {"t.me", "telegram.me"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    if parts[0] == "c" and len(parts) >= 3:
        chat_ref = f"c/{parts[1]}"
        message_part = parts[2]
    else:
        chat_ref = parts[0]
        message_part = parts[1]
    if not message_part.isdigit():
        return None
    return {"chat_ref": chat_ref, "message_id": int(message_part)}


def _find_source_message_by_link(
    session: Session,
    *,
    chat_ref: str | None,
    message_id: int | None,
) -> dict[str, Any] | None:
    if chat_ref is None or message_id is None:
        return None
    row = (
        session.execute(
            select(source_messages_table)
            .select_from(
                source_messages_table.join(
                    monitored_sources_table,
                    source_messages_table.c.monitored_source_id == monitored_sources_table.c.id,
                )
            )
            .where(
                source_messages_table.c.telegram_message_id == message_id,
                or_(
                    monitored_sources_table.c.username == chat_ref,
                    monitored_sources_table.c.input_ref == chat_ref,
                    monitored_sources_table.c.input_ref == f"@{chat_ref}",
                    monitored_sources_table.c.input_ref == f"https://t.me/{chat_ref}",
                ),
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _source_message_text(row: dict[str, Any] | None) -> str | None:
    if row is None:
        return None
    parts = [part for part in (row.get("text"), row.get("caption")) if part]
    return "\n".join(parts) if parts else None


def _create_classifier_example(
    session: Session,
    *,
    input_type: str,
    example_text: str,
    actor: str,
    raw_source_id: str | None,
    source_message_id: str | None,
    manual_input_id: str,
    evidence_note: str | None,
) -> dict[str, Any]:
    example_type, polarity, _expected_decision = EXAMPLE_INPUT_TYPES[input_type]
    now = utc_now()
    example_id = new_id()
    session.execute(
        insert(classifier_examples_table).values(
            id=example_id,
            example_type=example_type,
            polarity=polarity,
            status="active",
            source_message_id=source_message_id,
            raw_source_id=raw_source_id,
            lead_cluster_id=None,
            lead_event_id=None,
            category_id=None,
            catalog_item_id=None,
            catalog_term_id=None,
            reason_code=None,
            example_text=example_text,
            context_json={"manual_input_id": manual_input_id, "evidence_note": evidence_note},
            weight=1.0,
            created_from="manual_input",
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
    )
    row = (
        session.execute(
            select(classifier_examples_table).where(classifier_examples_table.c.id == example_id)
        )
        .mappings()
        .one()
    )
    session.commit()
    return dict(row)
