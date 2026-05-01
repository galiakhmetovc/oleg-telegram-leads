"""Request trace context helpers.

The stored shape intentionally mirrors OpenTelemetry identifiers:
``trace_id`` is 16 bytes as 32 lowercase hex chars and ``span_id`` is 8 bytes
as 16 lowercase hex chars. The app can export these rows to OTLP/Jaeger later
without changing domain tables.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from datetime import datetime
import re
import secrets
from typing import Any

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now

TRACE_CONTEXT_VERSION = "pur_leads.trace.v1"
TRACEPARENT_PATTERN = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-(?P<trace_flags>[0-9a-f]{2})$"
)
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")

_current_trace_context: ContextVar[TraceContext | None] = ContextVar(
    "pur_leads_trace_context",
    default=None,
)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    request_id: str
    started_at: datetime
    request_method: str | None = None
    request_path: str | None = None
    http_client_ip: str | None = None
    http_user_agent: str | None = None
    user_id: str | None = None
    web_session_id: str | None = None
    auth_method: str | None = None
    actor: str | None = None
    role: str | None = None
    sampled: bool = True

    @classmethod
    def for_request(
        cls,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        client_ip: str | None,
        user_agent: str | None,
    ) -> TraceContext:
        trace_id, parent_span_id, sampled = _ids_from_headers(headers)
        return cls(
            trace_id=trace_id,
            span_id=new_span_id(),
            parent_span_id=parent_span_id,
            request_id=_request_id_from_headers(headers),
            started_at=utc_now(),
            request_method=method,
            request_path=path,
            http_client_ip=client_ip,
            http_user_agent=user_agent,
            sampled=sampled,
        )

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "schema": TRACE_CONTEXT_VERSION,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "request_id": self.request_id,
            "request_method": self.request_method,
            "request_path": self.request_path,
            "user_id": self.user_id,
            "web_session_id": self.web_session_id,
            "auth_method": self.auth_method,
            "actor": self.actor,
            "role": self.role,
            "sampled": self.sampled,
        }

    def attributes(self) -> dict[str, Any]:
        return {
            "http.client_ip": self.http_client_ip,
            "http.user_agent": self.http_user_agent,
            "http.request.method": self.request_method,
            "url.path": self.request_path,
            "enduser.id": self.user_id,
            "pur.web_session_id": self.web_session_id,
            "pur.auth_method": self.auth_method,
            "pur.actor": self.actor,
            "pur.role": self.role,
        }


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


def current_trace_context() -> TraceContext | None:
    return _current_trace_context.get()


def set_trace_context(context: TraceContext) -> Token[TraceContext | None]:
    return _current_trace_context.set(context)


def reset_trace_context(token: Token[TraceContext | None]) -> None:
    _current_trace_context.reset(token)


def bind_trace_subject(
    *,
    user_id: str | None,
    web_session_id: str | None,
    auth_method: str | None,
    actor: str | None,
    role: str | None = None,
) -> TraceContext | None:
    context = current_trace_context()
    if context is None:
        return None
    updated = replace(
        context,
        user_id=user_id or context.user_id,
        web_session_id=web_session_id or context.web_session_id,
        auth_method=auth_method or context.auth_method,
        actor=actor or context.actor,
        role=role or context.role,
    )
    _current_trace_context.set(updated)
    return updated


def current_trace_json() -> dict[str, Any] | None:
    context = current_trace_context()
    return context.as_jsonable() if context is not None else None


def with_current_trace(value: Any) -> Any:
    trace = current_trace_json()
    if trace is None:
        return value
    if isinstance(value, dict):
        return {**value, "trace": trace}
    if value is None:
        return {"trace": trace}
    return {"value": value, "trace": trace}


def traceparent_value(context: TraceContext) -> str:
    flags = "01" if context.sampled else "00"
    return f"00-{context.trace_id}-{context.span_id}-{flags}"


def _ids_from_headers(headers: dict[str, str]) -> tuple[str, str | None, bool]:
    traceparent = headers.get("traceparent")
    if traceparent:
        match = TRACEPARENT_PATTERN.match(traceparent.strip().lower())
        if match and match.group("trace_id") != "0" * 32 and match.group("span_id") != "0" * 16:
            return (
                match.group("trace_id"),
                match.group("span_id"),
                int(match.group("trace_flags"), 16) & 1 == 1,
            )
    raw_trace_id = (headers.get("x-trace-id") or "").strip().lower()
    if TRACE_ID_PATTERN.match(raw_trace_id) and raw_trace_id != "0" * 32:
        parent_span_id = (headers.get("x-parent-span-id") or "").strip().lower()
        return (
            raw_trace_id,
            parent_span_id if SPAN_ID_PATTERN.match(parent_span_id) else None,
            True,
        )
    return new_trace_id(), None, True


def _request_id_from_headers(headers: dict[str, str]) -> str:
    value = (headers.get("x-request-id") or "").strip()
    return value[:128] if value else new_id()
