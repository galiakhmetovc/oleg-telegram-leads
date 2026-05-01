"""Persistence helpers for product-visible traces."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.core.tracing import TraceContext, current_trace_context, new_span_id
from pur_leads.models.tracing import (
    trace_span_events_table,
    trace_span_links_table,
    trace_spans_table,
)


class TraceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_span(
        self,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        span_name: str,
        span_kind: str,
        status: str,
        started_at: datetime,
        ended_at: datetime | None = None,
        status_message: str | None = None,
        user_id: str | None = None,
        web_session_id: str | None = None,
        actor: str | None = None,
        request_id: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        http_status_code: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        attributes_json: dict[str, Any] | None = None,
    ) -> str:
        span_pk = new_id()
        self.session.execute(
            insert(trace_spans_table).values(
                id=span_pk,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                span_name=span_name,
                span_kind=span_kind,
                status=status,
                status_message=status_message,
                user_id=user_id,
                web_session_id=web_session_id,
                actor=actor,
                request_id=request_id,
                request_method=request_method,
                request_path=request_path,
                http_status_code=http_status_code,
                resource_type=resource_type,
                resource_id=resource_id,
                attributes_json=_clean_attributes(attributes_json),
                started_at=started_at,
                ended_at=ended_at,
                created_at=utc_now(),
            )
        )
        self.session.commit()
        return span_pk

    def record_context_span(
        self,
        context: TraceContext,
        *,
        span_name: str,
        span_kind: str,
        status: str,
        ended_at: datetime | None = None,
        status_message: str | None = None,
        http_status_code: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        attributes_json: dict[str, Any] | None = None,
    ) -> str:
        attributes = {**context.attributes(), **(attributes_json or {})}
        return self.record_span(
            trace_id=context.trace_id,
            span_id=context.span_id,
            parent_span_id=context.parent_span_id,
            span_name=span_name,
            span_kind=span_kind,
            status=status,
            status_message=status_message,
            user_id=context.user_id,
            web_session_id=context.web_session_id,
            actor=context.actor,
            request_id=context.request_id,
            request_method=context.request_method,
            request_path=context.request_path,
            http_status_code=http_status_code,
            resource_type=resource_type,
            resource_id=resource_id,
            attributes_json=attributes,
            started_at=context.started_at,
            ended_at=ended_at or utc_now(),
        )

    def record_child_span(
        self,
        *,
        span_name: str,
        status: str,
        started_at: datetime,
        ended_at: datetime | None = None,
        status_message: str | None = None,
        span_kind: str = "internal",
        resource_type: str | None = None,
        resource_id: str | None = None,
        attributes_json: dict[str, Any] | None = None,
    ) -> str | None:
        context = current_trace_context()
        if context is None:
            return None
        child_span_id = new_span_id()
        attributes = {**context.attributes(), **(attributes_json or {})}
        return self.record_span(
            trace_id=context.trace_id,
            span_id=child_span_id,
            parent_span_id=context.span_id,
            span_name=span_name,
            span_kind=span_kind,
            status=status,
            status_message=status_message,
            user_id=context.user_id,
            web_session_id=context.web_session_id,
            actor=context.actor,
            request_id=context.request_id,
            request_method=context.request_method,
            request_path=context.request_path,
            resource_type=resource_type,
            resource_id=resource_id,
            attributes_json=attributes,
            started_at=started_at,
            ended_at=ended_at or utc_now(),
        )

    def record_event(
        self,
        *,
        event_name: str,
        severity: str = "info",
        entity_type: str | None = None,
        entity_id: str | None = None,
        attributes_json: dict[str, Any] | None = None,
    ) -> str | None:
        context = current_trace_context()
        if context is None:
            return None
        event_id = new_id()
        self.session.execute(
            insert(trace_span_events_table).values(
                id=event_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
                event_name=event_name,
                severity=severity,
                entity_type=entity_type,
                entity_id=entity_id,
                attributes_json=_clean_attributes(attributes_json),
                occurred_at=utc_now(),
            )
        )
        self.session.commit()
        return event_id

    def record_link(
        self,
        *,
        linked_trace_id: str,
        link_type: str,
        linked_span_id: str | None = None,
        attributes_json: dict[str, Any] | None = None,
    ) -> str | None:
        context = current_trace_context()
        if context is None:
            return None
        link_id = new_id()
        self.session.execute(
            insert(trace_span_links_table).values(
                id=link_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
                linked_trace_id=linked_trace_id,
                linked_span_id=linked_span_id,
                link_type=link_type,
                attributes_json=_clean_attributes(attributes_json),
                created_at=utc_now(),
            )
        )
        self.session.commit()
        return link_id


def _clean_attributes(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {key: item for key, item in value.items() if item is not None}
