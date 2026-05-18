from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import redis.asyncio as redis
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.infrastructure.persistence.runtime_retention import trim_enrichment_events
from app.infrastructure.persistence.runtime_retention import trim_notification_outbox
from app.infrastructure.persistence.tables import enrichment_events, enrichment_jobs
from app.infrastructure.persistence.tables import enrichment_results
from app.infrastructure.persistence.tables import enrichment_task_outbox
from app.infrastructure.persistence.tables import llm_settings, llm_verifications
from app.infrastructure.persistence.tables import nlp_config_revisions
from app.infrastructure.persistence.tables import notification_outbox
from app.infrastructure.persistence.tables import telegram_userbot_accounts
from app.infrastructure.persistence.tables import telegram_source_chats, telegram_source_messages


class PostgresRuntimeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_logs(
        self,
        *,
        limit: int,
        offset: int,
        service: str | None,
        level: str | None,
        q: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            logs = _logs_query().subquery("runtime_logs")
            conditions = _log_conditions(
                logs,
                service=service,
                level=level,
                q=q,
                created_from=created_from,
                created_to=created_to,
            )
            filtered = sa.select(logs).where(*conditions).subquery("filtered_runtime_logs")
            total_result = await session.execute(sa.select(sa.func.count()).select_from(filtered))
            rows_result = await session.execute(
                sa.select(filtered)
                .order_by(filtered.c.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        return {
            "total": int(total_result.scalar_one()),
            "items": [dict(row) for row in rows_result.mappings()],
        }

    async def enforce_log_retention(
        self,
        *,
        enrichment_event_rows: int,
        notification_outbox_rows: int,
    ) -> dict[str, int]:
        async with self._session_factory() as session:
            enrichment_deleted = await trim_enrichment_events(
                session,
                max_rows=enrichment_event_rows,
            )
            notification_deleted = await trim_notification_outbox(
                session,
                max_rows=notification_outbox_rows,
            )
            await session.commit()
        return {
            "enrichment_events_deleted": enrichment_deleted,
            "notification_outbox_deleted": notification_deleted,
        }

    async def system_status(self) -> list[dict[str, Any]]:
        settings = get_settings()
        checked_at = datetime.now(UTC)
        async with self._session_factory() as session:
            database_ok = await _database_ok(session)
            source_counts = await _counts_by_status(session, telegram_source_chats.c.status, telegram_source_chats)
            job_counts = await _counts_by_status(session, enrichment_jobs.c.status, enrichment_jobs)
            outbox_counts = await _counts_by_status(session, notification_outbox.c.status, notification_outbox)
            accounts_total = await _count_rows(session, telegram_userbot_accounts)
            accounts_enabled = await _count_rows(
                session,
                telegram_userbot_accounts,
                telegram_userbot_accounts.c.enabled.is_(True),
            )
            accounts_in_cooldown = await _count_rows(
                session,
                telegram_userbot_accounts,
                telegram_userbot_accounts.c.enabled.is_(True),
                telegram_userbot_accounts.c.cooldown_until > checked_at,
            )
            next_cooldown_until = await _min_value(
                session,
                telegram_userbot_accounts,
                telegram_userbot_accounts.c.cooldown_until,
                telegram_userbot_accounts.c.enabled.is_(True),
                telegram_userbot_accounts.c.cooldown_until > checked_at,
            )
            account_errors = await _latest_account_errors(session)
            source_chats_total = await _count_rows(session, telegram_source_chats)
            source_chats_enabled = await _count_rows(
                session,
                telegram_source_chats,
                telegram_source_chats.c.enabled.is_(True),
            )
            messages_total = await _count_rows(session, telegram_source_messages)
            latest_message_at = await _max_value(session, telegram_source_messages, telegram_source_messages.c.created_at)
            errored_sources = await _latest_source_errors(session)

            jobs_total = await _count_rows(session, enrichment_jobs)
            latest_job_created_at = await _max_value(session, enrichment_jobs, enrichment_jobs.c.created_at)
            latest_event_at = await _max_value(session, enrichment_events, enrichment_events.c.created_at)
            enrichment_events_retained = await _count_rows(session, enrichment_events)
            telegram_messages_enriched = await _telegram_messages_with_results(session)
            telegram_messages_failed_enrichment = await _telegram_messages_with_failed_jobs(session)
            telegram_messages_waiting_enrichment = max(
                messages_total - telegram_messages_enriched - telegram_messages_failed_enrichment,
                0,
            )
            latest_job_error = await _latest_failed_job_error(session)
            task_outbox_counts = await _counts_by_status(
                session,
                enrichment_task_outbox.c.status,
                enrichment_task_outbox,
            )
            task_outbox_total = await _count_rows(session, enrichment_task_outbox)
            latest_task_published_at = await _max_value(
                session,
                enrichment_task_outbox,
                enrichment_task_outbox.c.published_at,
            )
            oldest_task_pending_at = await _min_value(
                session,
                enrichment_task_outbox,
                enrichment_task_outbox.c.created_at,
                enrichment_task_outbox.c.status == "pending",
            )
            stale_task_sending = await _count_rows(
                session,
                enrichment_task_outbox,
                enrichment_task_outbox.c.status == "sending",
                enrichment_task_outbox.c.claimed_at < checked_at - timedelta(minutes=5),
            )
            pending_task_publish_errors = await _task_outbox_pending_with_errors(session)
            latest_task_publish_error = await _latest_task_publish_error(session)
            active_nlp_config_revision = await _active_nlp_config_revision(session)
            latest_worker_nlp_config_revision = await _latest_worker_nlp_config_revision(session)
            latest_worker_code_version = await _latest_worker_code_version(session)
            llm_run_counts = await _counts_by_status(session, llm_verifications.c.status, llm_verifications)
            llm_runs_total = await _count_rows(session, llm_verifications)
            oldest_llm_queued_at = await _min_value(
                session,
                llm_verifications,
                llm_verifications.c.created_at,
                llm_verifications.c.status == "queued",
            )
            oldest_llm_running_claimed_at = await _min_value(
                session,
                llm_verifications,
                llm_verifications.c.claimed_at,
                llm_verifications.c.status == "running",
            )
            latest_llm_completed_at = await _max_value(
                session,
                llm_verifications,
                llm_verifications.c.updated_at,
                llm_verifications.c.status == "completed",
            )
            latest_llm_error = await _latest_failed_llm_error(session)
            active_llm_settings = await _active_llm_settings(session)

            outbox_total = await _count_rows(session, notification_outbox)
            latest_notification_at = await _max_value(
                session,
                notification_outbox,
                sa.func.coalesce(notification_outbox.c.sent_at, notification_outbox.c.created_at),
            )
            oldest_pending_at = await _min_value(
                session,
                notification_outbox,
                notification_outbox.c.created_at,
                notification_outbox.c.status == "pending",
            )
            latest_notification_error = await _latest_failed_notification_error(session)
        redis_ok = await _redis_ok()
        llm_queue_depth = await _redis_queue_depth("llm")
        worker_code_stale = (
            latest_worker_code_version is not None and latest_worker_code_version != settings.code_version
        )
        worker_has_failed_jobs = bool(job_counts.get("failed", 0))
        stale_llm_running = (
            oldest_llm_running_claimed_at is not None
            and oldest_llm_running_claimed_at < checked_at - timedelta(minutes=30)
        )
        return [
            {
                "service": "backend",
                "status": "ok",
                "details": {
                    "environment": settings.environment,
                    "code_version": settings.code_version,
                    "process_role": settings.process_role,
                    "auth_enabled": settings.auth_enabled,
                    "public_base_url": settings.public_base_url,
                    "active_nlp_config_revision": (
                        active_nlp_config_revision["revision"] if active_nlp_config_revision else None
                    ),
                    "active_nlp_config_revision_id": (
                        str(active_nlp_config_revision["id"]) if active_nlp_config_revision else None
                    ),
                    "status_checked_at": checked_at,
                },
            },
            {
                "service": "postgres",
                "status": "ok" if database_ok else "error",
                "details": {"database_ok": database_ok, "status_checked_at": checked_at},
            },
            {
                "service": "redis",
                "status": "ok" if redis_ok else "error",
                "details": {"redis_ok": redis_ok, "status_checked_at": checked_at},
            },
            {
                "service": "userbot",
                "status": _userbot_status(
                    source_errors=source_counts.get("error", 0),
                    accounts_in_cooldown=accounts_in_cooldown,
                    account_errors=len(account_errors),
                ),
                "details": {
                    "accounts_total": accounts_total,
                    "accounts_enabled": accounts_enabled,
                    "accounts_in_cooldown": accounts_in_cooldown,
                    "next_cooldown_until": next_cooldown_until,
                    "account_errors": account_errors,
                    "source_chats_total": source_chats_total,
                    "source_chats_enabled": source_chats_enabled,
                    "source_chats_by_status": source_counts,
                    "messages_total": messages_total,
                    "latest_message_at": latest_message_at,
                    "errored_sources": errored_sources,
                },
            },
            {
                "service": "worker",
                "status": "warning" if worker_has_failed_jobs or worker_code_stale else "ok",
                "details": {
                    "jobs_total": jobs_total,
                    "jobs_by_status": job_counts,
                    "latest_job_created_at": latest_job_created_at,
                    "latest_event_at": latest_event_at,
                    "enrichment_events_retained": enrichment_events_retained,
                    "telegram_messages_enriched": telegram_messages_enriched,
                    "telegram_messages_waiting_enrichment": telegram_messages_waiting_enrichment,
                    "telegram_messages_failed_enrichment": telegram_messages_failed_enrichment,
                    "failed_latest_error": latest_job_error,
                    "backend_code_version": settings.code_version,
                    "latest_worker_code_version": latest_worker_code_version,
                    "worker_code_stale": worker_code_stale,
                    "active_nlp_config_revision": (
                        active_nlp_config_revision["revision"] if active_nlp_config_revision else None
                    ),
                    "active_nlp_config_revision_id": (
                        str(active_nlp_config_revision["id"]) if active_nlp_config_revision else None
                    ),
                    "latest_worker_nlp_config_revision": (
                        latest_worker_nlp_config_revision["revision"]
                        if latest_worker_nlp_config_revision
                        else None
                    ),
                    "latest_worker_nlp_config_revision_id": (
                        str(latest_worker_nlp_config_revision["id"])
                        if latest_worker_nlp_config_revision
                        else None
                    ),
                    "worker_config_stale": (
                        latest_worker_nlp_config_revision is not None
                        and active_nlp_config_revision is not None
                        and latest_worker_nlp_config_revision["id"] != active_nlp_config_revision["id"]
                    ),
                },
            },
            {
                "service": "llm-worker",
                "status": _llm_worker_status(
                    failed_runs=llm_run_counts.get("failed", 0),
                    stale_running=stale_llm_running,
                    redis_ok=redis_ok,
                ),
                "details": {
                    "model": active_llm_settings.get("model", settings.llm_verification_model),
                    "endpoint": active_llm_settings.get("endpoint", settings.llm_verification_endpoint),
                    "llm_enabled": active_llm_settings.get("enabled", True),
                    "execution_mode": "celery_queue:llm",
                    "redis_llm_queue_depth": llm_queue_depth,
                    "llm_runs_total": llm_runs_total,
                    "llm_runs_by_status": llm_run_counts,
                    "oldest_queued_at": oldest_llm_queued_at,
                    "oldest_running_claimed_at": oldest_llm_running_claimed_at,
                    "latest_completed_at": latest_llm_completed_at,
                    "failed_latest_error": latest_llm_error,
                },
            },
            {
                "service": "enrichment-dispatcher",
                "status": _enrichment_dispatcher_status(
                    pending_with_errors=pending_task_publish_errors,
                    stale_sending=stale_task_sending,
                ),
                "details": {
                    "task_outbox_total": task_outbox_total,
                    "task_outbox_by_status": task_outbox_counts,
                    "latest_task_published_at": latest_task_published_at,
                    "oldest_task_pending_at": oldest_task_pending_at,
                    "stale_task_sending": stale_task_sending,
                    "task_publish_latest_error": latest_task_publish_error,
                },
            },
            {
                "service": "notification-dispatcher",
                "status": "warning" if outbox_counts.get("failed", 0) else "ok",
                "details": {
                    "outbox_total": outbox_total,
                    "outbox_by_status": outbox_counts,
                    "latest_notification_at": latest_notification_at,
                    "oldest_pending_at": oldest_pending_at,
                    "failed_latest_error": latest_notification_error,
                },
            },
        ]


async def _database_ok(session: AsyncSession) -> bool:
    try:
        await session.execute(sa.text("select 1"))
        return True
    except Exception:
        return False


async def _redis_ok() -> bool:
    client = redis.from_url(get_settings().redis_url)
    try:
        return bool(await cast(Any, client.ping()))
    except Exception:
        return False
    finally:
        await client.aclose()


async def _redis_queue_depth(queue_name: str) -> int | None:
    client = redis.from_url(get_settings().redis_url)
    try:
        return int(await cast(Any, client.llen(queue_name)))
    except Exception:
        return None
    finally:
        await client.aclose()


async def _counts_by_status(
    session: AsyncSession,
    status_column: Any,
    table: sa.Table,
) -> dict[str, int]:
    result = await session.execute(
        sa.select(status_column, sa.func.count()).select_from(table).group_by(status_column)
    )
    return {str(status): int(count) for status, count in result.all()}


async def _count_rows(session: AsyncSession, table: sa.Table, *conditions: Any) -> int:
    result = await session.scalar(sa.select(sa.func.count()).select_from(table).where(*conditions))
    return int(result or 0)


async def _max_value(session: AsyncSession, table: sa.Table, column: Any, *conditions: Any) -> Any:
    return await session.scalar(sa.select(sa.func.max(column)).select_from(table).where(*conditions))


async def _min_value(session: AsyncSession, table: sa.Table, column: Any, *conditions: Any) -> Any:
    return await session.scalar(sa.select(sa.func.min(column)).select_from(table).where(*conditions))


async def _latest_source_errors(session: AsyncSession, limit: int = 5) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(
            telegram_source_chats.c.title,
            telegram_source_chats.c.status,
            telegram_source_chats.c.last_error,
            telegram_source_chats.c.updated_at,
        )
        .where(telegram_source_chats.c.last_error.is_not(None))
        .order_by(telegram_source_chats.c.updated_at.desc())
        .limit(limit)
    )
    return [dict(row) for row in result.mappings()]


async def _latest_account_errors(session: AsyncSession, limit: int = 5) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(
            telegram_userbot_accounts.c.name,
            telegram_userbot_accounts.c.status,
            telegram_userbot_accounts.c.last_error,
            telegram_userbot_accounts.c.cooldown_until,
            telegram_userbot_accounts.c.updated_at,
        )
        .where(telegram_userbot_accounts.c.last_error.is_not(None))
        .order_by(telegram_userbot_accounts.c.updated_at.desc())
        .limit(limit)
    )
    return [dict(row) for row in result.mappings()]


async def _latest_failed_job_error(session: AsyncSession) -> Any:
    result = await session.execute(
        sa.select(enrichment_jobs.c.error)
        .where(enrichment_jobs.c.status == "failed")
        .order_by(enrichment_jobs.c.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_failed_llm_error(session: AsyncSession) -> str | None:
    result = await session.execute(
        sa.select(llm_verifications.c.error)
        .where(llm_verifications.c.status == "failed")
        .where(llm_verifications.c.error.is_not(None))
        .order_by(llm_verifications.c.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _active_llm_settings(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(sa.select(llm_settings.c.config).where(llm_settings.c.id == "default"))
    config = result.scalar_one_or_none()
    return config if isinstance(config, dict) else {}


async def _active_nlp_config_revision(session: AsyncSession) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(
            nlp_config_revisions.c.id,
            nlp_config_revisions.c.revision,
            nlp_config_revisions.c.source,
            nlp_config_revisions.c.created_at,
        )
        .where(nlp_config_revisions.c.is_active.is_(True))
        .order_by(nlp_config_revisions.c.revision.desc())
        .limit(1)
    )
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def _latest_worker_nlp_config_revision(session: AsyncSession) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(
            enrichment_jobs.c.nlp_config_revision_id.label("id"),
            enrichment_jobs.c.nlp_config_revision.label("revision"),
            enrichment_jobs.c.updated_at,
        )
        .where(enrichment_jobs.c.nlp_config_revision_id.is_not(None))
        .where(enrichment_jobs.c.nlp_config_revision.is_not(None))
        .order_by(enrichment_jobs.c.updated_at.desc())
        .limit(1)
    )
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def _latest_worker_code_version(session: AsyncSession) -> str | None:
    result = await session.execute(
        sa.select(enrichment_events.c.payload)
        .where(
            enrichment_events.c.event_type.in_(
                ["job_started", "job_completed", "job_failed"],
            )
        )
        .order_by(enrichment_events.c.created_at.desc())
        .limit(50)
    )
    for payload in result.scalars():
        if not isinstance(payload, dict):
            continue
        code_version = payload.get("code_version")
        if code_version is None:
            continue
        process_role = payload.get("process_role")
        if process_role not in {None, "worker"}:
            continue
        return str(code_version)
    return None


async def _task_outbox_pending_with_errors(session: AsyncSession) -> int:
    return await _count_rows(
        session,
        enrichment_task_outbox,
        enrichment_task_outbox.c.status == "pending",
        enrichment_task_outbox.c.last_error.is_not(None),
    )


async def _latest_task_publish_error(session: AsyncSession) -> str | None:
    result = await session.execute(
        sa.select(enrichment_task_outbox.c.last_error)
        .where(enrichment_task_outbox.c.last_error.is_not(None))
        .order_by(enrichment_task_outbox.c.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _telegram_messages_with_results(session: AsyncSession) -> int:
    result = await session.scalar(
        sa.select(sa.func.count())
        .select_from(
            telegram_source_messages.join(
                enrichment_results,
                telegram_source_messages.c.enrichment_job_id == enrichment_results.c.job_id,
            )
        )
    )
    return int(result or 0)


async def _telegram_messages_with_failed_jobs(session: AsyncSession) -> int:
    result = await session.scalar(
        sa.select(sa.func.count())
        .select_from(
            telegram_source_messages.join(
                enrichment_jobs,
                telegram_source_messages.c.enrichment_job_id == enrichment_jobs.c.id,
            )
        )
        .where(enrichment_jobs.c.status == "failed")
    )
    return int(result or 0)


def _userbot_status(
    *,
    source_errors: int,
    accounts_in_cooldown: int,
    account_errors: int,
) -> str:
    if source_errors:
        return "error"
    if accounts_in_cooldown or account_errors:
        return "warning"
    return "ok"


def _enrichment_dispatcher_status(*, pending_with_errors: int, stale_sending: int) -> str:
    if stale_sending:
        return "error"
    if pending_with_errors:
        return "warning"
    return "ok"


def _llm_worker_status(*, failed_runs: int, stale_running: bool, redis_ok: bool) -> str:
    if not redis_ok or stale_running:
        return "error"
    if failed_runs:
        return "warning"
    return "ok"


async def _latest_failed_notification_error(session: AsyncSession) -> str | None:
    result = await session.execute(
        sa.select(notification_outbox.c.last_error)
        .where(notification_outbox.c.status == "failed")
        .order_by(notification_outbox.c.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _logs_query() -> sa.CompoundSelect[Any]:
    return sa.union_all(
        _enrichment_logs_query(),
        _enrichment_task_dispatcher_logs_query(),
        _telegram_logs_query(),
        _notification_logs_query(),
        _account_error_logs_query(),
        _source_error_logs_query(),
    )


def _log_conditions(
    logs: Any,
    *,
    service: str | None,
    level: str | None,
    q: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> list[Any]:
    conditions = []
    if service:
        conditions.append(logs.c.service == service)
    if level:
        conditions.append(logs.c.level == level)
    if q:
        conditions.append(logs.c.message.ilike(f"%{q}%"))
    if created_from:
        conditions.append(logs.c.created_at >= created_from)
    if created_to:
        conditions.append(logs.c.created_at <= created_to)
    return conditions


def _enrichment_logs_query() -> sa.Select[Any]:
    return sa.select(
        enrichment_events.c.created_at.label("created_at"),
        sa.literal("worker").label("service"),
        sa.case(
            (enrichment_events.c.event_type == "job_failed", sa.literal("error")),
            else_=sa.literal("info"),
        ).label("level"),
        enrichment_events.c.message.label("message"),
        sa.func.jsonb_build_object(
            "event_type",
            enrichment_events.c.event_type,
            "job_id",
            sa.cast(enrichment_events.c.job_id, sa.Text()),
            "progress_percent",
            enrichment_events.c.progress_percent,
        ).label("payload"),
    )


def _enrichment_task_dispatcher_logs_query() -> sa.Select[Any]:
    return sa.select(
        sa.func.coalesce(
            enrichment_task_outbox.c.published_at,
            enrichment_task_outbox.c.updated_at,
            enrichment_task_outbox.c.created_at,
        ).label("created_at"),
        sa.literal("enrichment-dispatcher").label("service"),
        sa.case(
            (
                enrichment_task_outbox.c.last_error.is_not(None)
                & (enrichment_task_outbox.c.status != "published"),
                sa.literal("error"),
            ),
            else_=sa.literal("info"),
        ).label("level"),
        sa.func.concat(sa.literal("Публикация enrichment-задачи "), enrichment_task_outbox.c.status).label("message"),
        sa.func.jsonb_build_object(
            "job_id",
            sa.cast(enrichment_task_outbox.c.job_id, sa.Text()),
            "task_name",
            enrichment_task_outbox.c.task_name,
            "status",
            enrichment_task_outbox.c.status,
            "attempts",
            enrichment_task_outbox.c.attempts,
            "last_error",
            enrichment_task_outbox.c.last_error,
        ).label("payload"),
    )


def _telegram_logs_query() -> sa.Select[Any]:
    return (
        sa.select(
            telegram_source_messages.c.created_at.label("created_at"),
            sa.literal("userbot").label("service"),
            sa.literal("info").label("level"),
            sa.func.concat(
                sa.literal("Получено сообщение Telegram из "),
                telegram_source_chats.c.title,
            ).label("message"),
            sa.func.jsonb_build_object(
                "source_chat_id",
                sa.cast(telegram_source_messages.c.source_chat_id, sa.Text()),
                "telegram_message_id",
                telegram_source_messages.c.telegram_message_id,
                "enrichment_job_id",
                sa.cast(telegram_source_messages.c.enrichment_job_id, sa.Text()),
            ).label("payload"),
        )
        .select_from(
            telegram_source_messages.join(
                telegram_source_chats,
                telegram_source_messages.c.source_chat_id == telegram_source_chats.c.id,
            )
        )
    )


def _notification_logs_query() -> sa.Select[Any]:
    return sa.select(
        sa.func.coalesce(notification_outbox.c.sent_at, notification_outbox.c.created_at).label("created_at"),
        sa.literal("notification-dispatcher").label("service"),
        sa.case(
            (notification_outbox.c.status == "failed", sa.literal("error")),
            else_=sa.literal("info"),
        ).label("level"),
        sa.func.concat(sa.literal("Уведомление "), notification_outbox.c.status).label("message"),
        sa.func.jsonb_build_object(
            "route_id",
            notification_outbox.c.route_id,
            "bot_id",
            notification_outbox.c.bot_id,
            "chat_id",
            notification_outbox.c.chat_id,
            "attempts",
            notification_outbox.c.attempts,
            "last_error",
            notification_outbox.c.last_error,
        ).label("payload"),
    )


def _source_error_logs_query() -> sa.Select[Any]:
    return (
        sa.select(
            telegram_source_chats.c.updated_at.label("created_at"),
            sa.literal("userbot").label("service"),
            sa.literal("error").label("level"),
            sa.func.concat(
                sa.literal("Ошибка источника "),
                telegram_source_chats.c.title,
                sa.literal(": "),
                telegram_source_chats.c.last_error,
            ).label("message"),
            sa.func.jsonb_build_object(
                "source_chat_id",
                sa.cast(telegram_source_chats.c.id, sa.Text()),
                "input_ref",
                telegram_source_chats.c.input_ref,
                "status",
                telegram_source_chats.c.status,
            ).label("payload"),
        )
        .where(telegram_source_chats.c.last_error.is_not(None))
    )


def _account_error_logs_query() -> sa.Select[Any]:
    return (
        sa.select(
            telegram_userbot_accounts.c.updated_at.label("created_at"),
            sa.literal("userbot").label("service"),
            sa.literal("error").label("level"),
            sa.func.concat(
                sa.literal("Ошибка аккаунта "),
                telegram_userbot_accounts.c.name,
                sa.literal(": "),
                telegram_userbot_accounts.c.last_error,
            ).label("message"),
            sa.func.jsonb_build_object(
                "account_id",
                sa.cast(telegram_userbot_accounts.c.id, sa.Text()),
                "status",
                telegram_userbot_accounts.c.status,
                "cooldown_until",
                telegram_userbot_accounts.c.cooldown_until,
            ).label("payload"),
        )
        .where(telegram_userbot_accounts.c.last_error.is_not(None))
    )
