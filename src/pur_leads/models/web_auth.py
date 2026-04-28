"""Web authentication table definitions."""

from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table

metadata = MetaData()

web_users_table = Table(
    "web_users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("telegram_user_id", String(80), nullable=True),
    Column("telegram_username", String(160), nullable=True),
    Column("display_name", String(255), nullable=True),
    Column("auth_type", String(32), nullable=False),
    Column("local_username", String(160), nullable=True),
    Column("password_hash", String(512), nullable=True),
    Column("must_change_password", Boolean, nullable=False),
    Column("role", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
)

web_auth_sessions_table = Table(
    "web_auth_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("auth_method", String(32), nullable=False),
    Column("session_token_hash", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("ip_address", String(64), nullable=True),
    Column("user_agent", String(512), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)
