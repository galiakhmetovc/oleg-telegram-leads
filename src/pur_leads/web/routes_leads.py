"""Lead inbox and feedback routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session

from pur_leads.models.catalog import (
    catalog_categories_table,
    catalog_items_table,
    catalog_terms_table,
)
from pur_leads.models.leads import lead_clusters_table, lead_events_table, lead_matches_table
from pur_leads.models.telegram_sources import sender_profiles_table, source_messages_table
from pur_leads.services.lead_inbox import LeadInboxFilters, LeadInboxService
from pur_leads.services.leads import LeadService
from pur_leads.services.web_auth import SessionValidationResult
from pur_leads.web.dependencies import current_admin, get_session

router = APIRouter(prefix="/api")


class LeadActionRequest(BaseModel):
    action: str
    reason_code: str | None = None
    comment: str | None = None
    snoozed_until: datetime | None = None
    duplicate_of_cluster_id: str | None = None
    lead_event_id: str | None = None


class FeedbackRequest(BaseModel):
    target_type: str
    target_id: str
    action: str
    reason_code: str | None = None
    feedback_scope: str | None = None
    learning_effect: str | None = None
    application_status: str = "recorded"
    applied_entity_type: str | None = None
    applied_entity_id: str | None = None
    comment: str | None = None
    metadata_json: Any | None = None


class TargetFeedbackRequest(BaseModel):
    action: str
    reason_code: str | None = None
    feedback_scope: str | None = None
    learning_effect: str | None = None
    application_status: str = "recorded"
    applied_entity_type: str | None = None
    applied_entity_id: str | None = None
    comment: str | None = None
    metadata_json: Any | None = None


@router.get("/leads")
def list_leads(
    status: str | None = None,
    source_id: str | None = None,
    source: str | None = None,
    category_id: str | None = None,
    category: str | None = None,
    retro: bool | None = None,
    maybe: bool | None = None,
    auto_pending: bool | None = None,
    operator_issues: bool | None = None,
    min_confidence: float | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    filters = LeadInboxFilters(
        status=status,
        source_id=source_id or source,
        category_id=category_id or category,
        retro=retro,
        maybe=maybe,
        auto_pending=auto_pending,
        operator_issues=operator_issues,
        min_confidence=min_confidence,
    )
    rows = LeadInboxService(session).list_cluster_queue(filters)
    return {"items": jsonable_encoder(rows)}


@router.get("/leads/{cluster_id}")
def get_lead_detail(
    cluster_id: str,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        detail = LeadInboxService(session).get_cluster_detail(cluster_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lead cluster not found") from exc
    return jsonable_encoder(detail)


@router.post("/leads/{cluster_id}/actions")
def apply_lead_action(
    cluster_id: str,
    payload: LeadActionRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = LeadService(session)
    actor = _actor(validated)
    action = _ACTION_ALIASES.get(payload.action, payload.action)
    try:
        if action == "take_into_work":
            result = service.take_into_work(
                cluster_id,
                actor=actor,
                owner_user_id=validated.user.id,
            )
            return jsonable_encoder(result)

        feedback = service.apply_cluster_action(
            cluster_id,
            action=action,
            actor=actor,
            reason_code=payload.reason_code,
            comment=payload.comment,
            snoozed_until=payload.snoozed_until,
            duplicate_of_cluster_id=payload.duplicate_of_cluster_id,
            lead_event_id=payload.lead_event_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lead cluster or target not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"feedback": jsonable_encoder(feedback)}


@router.post("/feedback")
def record_feedback(
    payload: FeedbackRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _record_feedback(payload, validated=validated, session=session)


@router.post("/feedback/{target_type}/{target_id}")
def record_target_feedback(
    target_type: str,
    target_id: str,
    payload: TargetFeedbackRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _record_feedback(
        FeedbackRequest(
            target_type=target_type,
            target_id=target_id,
            action=payload.action,
            reason_code=payload.reason_code,
            feedback_scope=payload.feedback_scope,
            learning_effect=payload.learning_effect,
            application_status=payload.application_status,
            applied_entity_type=payload.applied_entity_type,
            applied_entity_id=payload.applied_entity_id,
            comment=payload.comment,
            metadata_json=payload.metadata_json,
        ),
        validated=validated,
        session=session,
    )


def _record_feedback(
    payload: FeedbackRequest,
    *,
    validated: SessionValidationResult,
    session: Session,
) -> dict[str, Any]:
    target_type = _FEEDBACK_TARGET_TYPE_ALIASES.get(payload.target_type, payload.target_type)
    if target_type not in _ALLOWED_FEEDBACK_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported feedback target_type")
    _validate_feedback_enums(payload)
    if not _target_exists(session, target_type=target_type, target_id=payload.target_id):
        raise HTTPException(status_code=404, detail="Feedback target not found")
    if (payload.applied_entity_type is None) != (payload.applied_entity_id is None):
        raise HTTPException(
            status_code=400,
            detail="applied_entity_type and applied_entity_id must be provided together",
        )
    applied_entity_type = None
    if payload.applied_entity_type is not None and payload.applied_entity_id is not None:
        applied_entity_type = _FEEDBACK_TARGET_TYPE_ALIASES.get(
            payload.applied_entity_type, payload.applied_entity_type
        )
        if applied_entity_type not in _ALLOWED_FEEDBACK_TARGET_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported applied_entity_type")
        if not _target_exists(
            session,
            target_type=applied_entity_type,
            target_id=payload.applied_entity_id,
        ):
            raise HTTPException(status_code=404, detail="Applied entity not found")
    try:
        feedback = LeadService(session).record_feedback(
            target_type=target_type,
            target_id=payload.target_id,
            action=payload.action,
            reason_code=payload.reason_code,
            feedback_scope=payload.feedback_scope,
            learning_effect=payload.learning_effect,
            application_status=payload.application_status,
            applied_entity_type=applied_entity_type,
            applied_entity_id=payload.applied_entity_id,
            comment=payload.comment,
            metadata_json=payload.metadata_json,
            created_by=_actor(validated),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"feedback": jsonable_encoder(feedback)}


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _validate_feedback_enums(payload: FeedbackRequest) -> None:
    if payload.application_status not in _ALLOWED_ROUTE_APPLICATION_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported application_status")
    if (
        payload.feedback_scope is not None
        and payload.feedback_scope not in _ALLOWED_FEEDBACK_SCOPES
    ):
        raise HTTPException(status_code=400, detail="Unsupported feedback_scope")
    if (
        payload.learning_effect is not None
        and payload.learning_effect not in _ALLOWED_LEARNING_EFFECTS
    ):
        raise HTTPException(status_code=400, detail="Unsupported learning_effect")


def _target_exists(session: Session, *, target_type: str, target_id: str) -> bool:
    column = _TARGET_ID_COLUMNS[target_type]
    count = session.scalar(
        select(func.count()).select_from(column.table).where(column == target_id)
    )
    return bool(count)


_ACTION_ALIASES = {
    "confirm": "lead_confirmed",
    "lead_confirmed": "lead_confirmed",
    "take_into_work": "take_into_work",
    "not_lead": "not_lead",
    "maybe": "maybe",
    "snooze": "snooze",
    "duplicate": "duplicate",
    "context_only": "mark_context_only",
    "mark_context_only": "mark_context_only",
}

_FEEDBACK_TARGET_TYPE_ALIASES = {
    "cluster": "lead_cluster",
    "event": "lead_event",
    "match": "lead_match",
    "term": "catalog_term",
    "item": "catalog_item",
    "category": "category",
    "catalog_category": "category",
    "sender": "sender_profile",
    "telegram_sender": "sender_profile",
    "message": "source_message",
}

_ALLOWED_FEEDBACK_TARGET_TYPES = {
    "lead_cluster",
    "lead_event",
    "lead_match",
    "catalog_term",
    "catalog_item",
    "category",
    "sender_profile",
    "source_message",
}

_ALLOWED_ROUTE_APPLICATION_STATUSES = {
    "recorded",
    "queued",
    "needs_review",
    "ignored",
}

_ALLOWED_FEEDBACK_SCOPES = {
    "classifier",
    "catalog",
    "clustering",
    "crm_outcome",
    "source_quality",
    "manual_example",
    "none",
}

_ALLOWED_LEARNING_EFFECTS = {
    "positive_example",
    "negative_example",
    "match_correction",
    "term_weight_down",
    "term_review",
    "sender_role_hint",
    "cluster_training",
    "source_quality_signal",
    "no_classifier_learning",
}

_TARGET_ID_COLUMNS: dict[str, ColumnElement[Any]] = {
    "lead_cluster": lead_clusters_table.c.id,
    "lead_event": lead_events_table.c.id,
    "lead_match": lead_matches_table.c.id,
    "catalog_term": catalog_terms_table.c.id,
    "catalog_item": catalog_items_table.c.id,
    "category": catalog_categories_table.c.id,
    "sender_profile": sender_profiles_table.c.id,
    "source_message": source_messages_table.c.id,
}
