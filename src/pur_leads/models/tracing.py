"""OpenTelemetry-compatible product tracing table definitions."""

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, Text

metadata = MetaData()

trace_spans_table = Table(
    "trace_spans",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("trace_id", String(32), nullable=False),
    Column("span_id", String(16), nullable=False),
    Column("parent_span_id", String(16), nullable=True),
    Column("span_name", String(240), nullable=False),
    Column("span_kind", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("status_message", Text, nullable=True),
    Column("user_id", String(36), nullable=True),
    Column("web_session_id", String(36), nullable=True),
    Column("actor", String(160), nullable=True),
    Column("request_id", String(128), nullable=True),
    Column("request_method", String(16), nullable=True),
    Column("request_path", String(512), nullable=True),
    Column("http_status_code", Integer, nullable=True),
    Column("resource_type", String(120), nullable=True),
    Column("resource_id", String(128), nullable=True),
    Column("attributes_json", JSON, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

trace_span_events_table = Table(
    "trace_span_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("trace_id", String(32), nullable=False),
    Column("span_id", String(16), nullable=False),
    Column("event_name", String(240), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("entity_type", String(120), nullable=True),
    Column("entity_id", String(128), nullable=True),
    Column("attributes_json", JSON, nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

trace_span_links_table = Table(
    "trace_span_links",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("trace_id", String(32), nullable=False),
    Column("span_id", String(16), nullable=False),
    Column("linked_trace_id", String(32), nullable=False),
    Column("linked_span_id", String(16), nullable=True),
    Column("link_type", String(80), nullable=False),
    Column("attributes_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
