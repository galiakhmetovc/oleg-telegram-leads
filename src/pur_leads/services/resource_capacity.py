"""Resource capacity calculation for workers, AI models, and Telegram accounts."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pur_leads.core.time import utc_now
from pur_leads.models.ai import (
    ai_agent_routes_table,
    ai_agents_table,
    ai_model_concurrency_leases_table,
    ai_model_limits_table,
    ai_models_table,
    ai_provider_accounts_table,
    ai_providers_table,
)
from pur_leads.models.scheduler import scheduler_jobs_table
from pur_leads.models.telegram_sources import telegram_bots_table, userbot_accounts_table
from pur_leads.services.ai_registry import DEFAULT_UTILIZATION_RATIO
from pur_leads.services.settings import SettingsService


class ResourceCapacityService:
    """Build an advisory capacity report from configured resources and active leases."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = SettingsService(session)

    def capacity_report(self) -> dict[str, Any]:
        now = utc_now()
        ai_model_pools = self._ai_model_pools(now=now)
        telegram_userbot_pools = self._telegram_userbot_pools()
        telegram_bot_pools = self._telegram_bot_pools()
        local_parser_pool = self._local_pool(
            pool_key="local_parser",
            display_name="Local PDF/text parser",
            capability="local.parse",
            setting_key="local_parser_concurrency",
            default=4,
        )
        external_fetch_pool = self._local_pool(
            pool_key="external_fetch",
            display_name="External page fetch",
            capability="external.fetch",
            setting_key="external_page_fetch_concurrency",
            default=4,
        )
        route_capacities = self._agent_route_capacities(ai_model_pools)
        job_demand = self._job_demand()
        totals = _totals(
            ai_model_pools=ai_model_pools,
            telegram_userbot_pools=telegram_userbot_pools,
            telegram_bot_pools=telegram_bot_pools,
            local_parser_pool=local_parser_pool,
            external_fetch_pool=external_fetch_pool,
        )
        worker_capacity = self._worker_capacity(totals)
        bottlenecks = self._bottlenecks(
            worker_capacity=worker_capacity,
            totals=totals,
            route_capacities=route_capacities,
        )
        return {
            "worker_capacity": worker_capacity,
            "totals": totals,
            "ai_model_pools": ai_model_pools,
            "telegram_userbot_pools": telegram_userbot_pools,
            "telegram_bot_pools": telegram_bot_pools,
            "local_pools": [local_parser_pool, external_fetch_pool],
            "agent_route_capacities": route_capacities,
            "job_demand": job_demand,
            "bottlenecks": bottlenecks,
        }

    def _ai_model_pools(self, *, now) -> list[dict[str, Any]]:  # noqa: ANN001
        lease_counts = self._active_ai_lease_counts(now=now)
        rows = (
            self.session.execute(
                select(
                    ai_provider_accounts_table.c.id.label("provider_account_id"),
                    ai_provider_accounts_table.c.display_name.label("provider_account_name"),
                    ai_provider_accounts_table.c.priority.label("provider_account_priority"),
                    ai_providers_table.c.provider_key,
                    ai_providers_table.c.display_name.label("provider_name"),
                    ai_models_table.c.id.label("model_id"),
                    ai_models_table.c.provider_model_name,
                    ai_models_table.c.normalized_model_name,
                    ai_models_table.c.display_name.label("model_display_name"),
                    ai_models_table.c.model_type,
                    ai_models_table.c.supports_structured_output,
                    ai_models_table.c.supports_json_mode,
                    ai_models_table.c.supports_thinking,
                    ai_models_table.c.supports_tools,
                    ai_models_table.c.supports_streaming,
                    ai_models_table.c.supports_image_input,
                    ai_models_table.c.supports_document_input,
                    ai_models_table.c.metadata_json.label("model_metadata_json"),
                    ai_model_limits_table.c.raw_limit,
                    ai_model_limits_table.c.utilization_ratio,
                    ai_model_limits_table.c.effective_limit,
                    ai_model_limits_table.c.source.label("limit_source"),
                )
                .select_from(
                    ai_provider_accounts_table.join(
                        ai_providers_table,
                        ai_provider_accounts_table.c.ai_provider_id == ai_providers_table.c.id,
                    )
                    .join(
                        ai_models_table,
                        ai_models_table.c.ai_provider_id == ai_providers_table.c.id,
                    )
                    .outerjoin(
                        ai_model_limits_table,
                        (ai_model_limits_table.c.ai_model_id == ai_models_table.c.id)
                        & (ai_model_limits_table.c.limit_scope == "concurrency"),
                    )
                )
                .where(
                    ai_provider_accounts_table.c.enabled.is_(True),
                    ai_providers_table.c.status == "active",
                    ai_models_table.c.status == "active",
                )
                .order_by(
                    ai_provider_accounts_table.c.priority,
                    ai_providers_table.c.provider_key,
                    ai_models_table.c.model_type,
                    ai_models_table.c.normalized_model_name,
                )
            )
            .mappings()
            .all()
        )
        pools: list[dict[str, Any]] = []
        for row in rows:
            raw_limit = _positive_int(row["raw_limit"], default=1)
            utilization_ratio = _ratio(row["utilization_ratio"], default=DEFAULT_UTILIZATION_RATIO)
            effective_limit = _positive_int(
                row["effective_limit"],
                default=_effective_limit(raw_limit, utilization_ratio),
            )
            key = (
                str(row["provider_account_id"]),
                str(row["provider_key"]),
                str(row["normalized_model_name"]),
            )
            used_slots = lease_counts.get(key, 0)
            model_metadata = row["model_metadata_json"] or {}
            if not isinstance(model_metadata, dict):
                model_metadata = {}
            endpoint_family = model_metadata.get("endpoint_family")
            pools.append(
                {
                    "pool_key": (
                        f"ai:{row['provider_key']}:{row['provider_account_id']}:"
                        f"{row['normalized_model_name']}"
                    ),
                    "resource_type": "ai_model",
                    "provider": row["provider_key"],
                    "provider_name": row["provider_name"],
                    "provider_account_id": row["provider_account_id"],
                    "provider_account_name": row["provider_account_name"],
                    "model_id": row["model_id"],
                    "provider_model_name": row["provider_model_name"],
                    "normalized_model_name": row["normalized_model_name"],
                    "model_display_name": row["model_display_name"],
                    "model_type": row["model_type"],
                    "endpoint_family": endpoint_family,
                    "supports_structured_output": bool(row["supports_structured_output"]),
                    "supports_json_mode": bool(row["supports_json_mode"]),
                    "supports_thinking": bool(row["supports_thinking"]),
                    "supports_tools": bool(row["supports_tools"]),
                    "supports_streaming": bool(row["supports_streaming"]),
                    "supports_image_input": bool(row["supports_image_input"]),
                    "supports_document_input": bool(row["supports_document_input"]),
                    "capabilities": _ai_capabilities(
                        str(row["model_type"]),
                        endpoint_family=str(endpoint_family) if endpoint_family else None,
                        supports_structured_output=bool(row["supports_structured_output"]),
                        supports_json_mode=bool(row["supports_json_mode"]),
                        supports_thinking=bool(row["supports_thinking"]),
                        supports_image_input=bool(row["supports_image_input"]),
                        supports_document_input=bool(row["supports_document_input"]),
                    ),
                    "raw_limit": raw_limit,
                    "utilization_ratio": utilization_ratio,
                    "effective_limit": effective_limit,
                    "used_slots": used_slots,
                    "available_slots": max(0, effective_limit - used_slots),
                    "status": "active",
                    "limit_source": row["limit_source"] or "default",
                }
            )
        return pools

    def _active_ai_lease_counts(self, *, now) -> Counter[tuple[str, str, str]]:  # noqa: ANN001
        rows = (
            self.session.execute(
                select(
                    ai_model_concurrency_leases_table.c.ai_provider_account_id,
                    ai_model_concurrency_leases_table.c.provider,
                    ai_model_concurrency_leases_table.c.normalized_model,
                    func.count().label("count"),
                )
                .where(ai_model_concurrency_leases_table.c.lease_expires_at > now)
                .group_by(
                    ai_model_concurrency_leases_table.c.ai_provider_account_id,
                    ai_model_concurrency_leases_table.c.provider,
                    ai_model_concurrency_leases_table.c.normalized_model,
                )
            )
            .mappings()
            .all()
        )
        counts: Counter[tuple[str, str, str]] = Counter()
        for row in rows:
            account_id = row["ai_provider_account_id"]
            if account_id is None:
                continue
            counts[(str(account_id), str(row["provider"]), str(row["normalized_model"]))] = int(
                row["count"]
            )
        return counts

    def _telegram_userbot_pools(self) -> list[dict[str, Any]]:
        rows = (
            self.session.execute(
                select(userbot_accounts_table)
                .where(userbot_accounts_table.c.status == "active")
                .order_by(userbot_accounts_table.c.created_at)
            )
            .mappings()
            .all()
        )
        pools: list[dict[str, Any]] = []
        for row in rows:
            raw_limit = _positive_int(row["max_parallel_telegram_jobs"], default=1)
            effective_limit = raw_limit
            pools.append(
                {
                    "pool_key": f"telegram_userbot:{row['id']}",
                    "resource_type": "telegram_userbot",
                    "userbot_account_id": row["id"],
                    "display_name": row["display_name"],
                    "telegram_username": row["telegram_username"],
                    "capabilities": ["telegram.read_history", "telegram.download_document"],
                    "raw_limit": raw_limit,
                    "effective_limit": effective_limit,
                    "used_slots": 0,
                    "available_slots": effective_limit,
                    "status": row["status"],
                    "scheduler_note": "bounded by userbot max_parallel_telegram_jobs",
                }
            )
        return pools

    def _telegram_bot_pools(self) -> list[dict[str, Any]]:
        per_bot_limit = _positive_int(
            self.settings.get("telegram_bot_send_concurrency_per_bot"),
            default=1,
        )
        rows = (
            self.session.execute(
                select(telegram_bots_table)
                .where(telegram_bots_table.c.status == "active")
                .order_by(telegram_bots_table.c.created_at)
            )
            .mappings()
            .all()
        )
        return [
            {
                "pool_key": f"telegram_bot:{row['id']}",
                "resource_type": "telegram_bot",
                "telegram_bot_id": row["id"],
                "display_name": row["display_name"],
                "telegram_username": row["telegram_username"],
                "capabilities": ["telegram.notify", "telegram.delete_message"],
                "raw_limit": per_bot_limit,
                "effective_limit": per_bot_limit,
                "used_slots": 0,
                "available_slots": per_bot_limit,
                "status": row["status"],
            }
            for row in rows
        ]

    def _local_pool(
        self,
        *,
        pool_key: str,
        display_name: str,
        capability: str,
        setting_key: str,
        default: int,
    ) -> dict[str, Any]:
        effective_limit = _positive_int(self.settings.get(setting_key), default=default)
        return {
            "pool_key": pool_key,
            "resource_type": pool_key,
            "display_name": display_name,
            "capabilities": [capability],
            "raw_limit": effective_limit,
            "effective_limit": effective_limit,
            "used_slots": 0,
            "available_slots": effective_limit,
            "status": "active",
            "setting_key": setting_key,
        }

    def _agent_route_capacities(self, ai_model_pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pool_by_account_model = {
            (pool["provider_account_id"], pool["model_id"]): pool for pool in ai_model_pools
        }
        rows = (
            self.session.execute(
                select(
                    ai_agents_table.c.agent_key,
                    ai_agents_table.c.task_type,
                    ai_agent_routes_table.c.route_role,
                    ai_agent_routes_table.c.priority,
                    ai_provider_accounts_table.c.id.label("provider_account_id"),
                    ai_models_table.c.id.label("model_id"),
                    ai_providers_table.c.provider_key,
                    ai_models_table.c.provider_model_name,
                    ai_models_table.c.model_type,
                )
                .select_from(
                    ai_agent_routes_table.join(
                        ai_agents_table,
                        ai_agent_routes_table.c.ai_agent_id == ai_agents_table.c.id,
                    )
                    .join(
                        ai_provider_accounts_table,
                        ai_agent_routes_table.c.ai_provider_account_id
                        == ai_provider_accounts_table.c.id,
                    )
                    .join(
                        ai_models_table,
                        ai_agent_routes_table.c.ai_model_id == ai_models_table.c.id,
                    )
                    .join(
                        ai_providers_table,
                        ai_models_table.c.ai_provider_id == ai_providers_table.c.id,
                    )
                )
                .where(
                    ai_agents_table.c.enabled.is_(True),
                    ai_agent_routes_table.c.enabled.is_(True),
                    ai_provider_accounts_table.c.enabled.is_(True),
                    ai_providers_table.c.status == "active",
                    ai_models_table.c.status == "active",
                )
                .order_by(ai_agents_table.c.agent_key, ai_agent_routes_table.c.priority)
            )
            .mappings()
            .all()
        )
        capacities: list[dict[str, Any]] = []
        for row in rows:
            pool = pool_by_account_model.get((row["provider_account_id"], row["model_id"]))
            if pool is None:
                continue
            capacities.append(
                {
                    "agent_key": row["agent_key"],
                    "task_type": row["task_type"],
                    "route_role": row["route_role"],
                    "priority": row["priority"],
                    "provider": row["provider_key"],
                    "provider_account_id": row["provider_account_id"],
                    "model_id": row["model_id"],
                    "model": row["provider_model_name"],
                    "model_type": row["model_type"],
                    "pool_key": pool["pool_key"],
                    "effective_limit": pool["effective_limit"],
                    "used_slots": pool["used_slots"],
                    "available_slots": pool["available_slots"],
                }
            )
        return capacities

    def _job_demand(self) -> dict[str, Any]:
        rows = (
            self.session.execute(
                select(
                    scheduler_jobs_table.c.status,
                    scheduler_jobs_table.c.job_type,
                    func.count().label("count"),
                )
                .where(scheduler_jobs_table.c.status.in_(["queued", "running"]))
                .group_by(scheduler_jobs_table.c.status, scheduler_jobs_table.c.job_type)
            )
            .mappings()
            .all()
        )
        by_status: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)
        for row in rows:
            count = int(row["count"])
            by_status[str(row["status"])] += count
            by_type[str(row["job_type"])] += count
        return {
            "by_status": dict(by_status),
            "by_type": dict(by_type),
            "total_active": sum(by_status.values()),
        }

    def _worker_capacity(self, totals: dict[str, int]) -> dict[str, Any]:
        configured = _positive_int(self.settings.get("worker_concurrency"), default=1)
        global_cap = _positive_int(self.settings.get("worker_capacity_global_cap"), default=32)
        realtime_reserve = max(
            0,
            int(_positive_int(self.settings.get("worker_realtime_reserved_slots"), default=2)),
        )
        resource_limited = max(
            1,
            totals["ai_model_effective_slots"]
            + totals["telegram_userbot_effective_slots"]
            + totals["telegram_bot_effective_slots"]
            + totals["local_parser_effective_slots"]
            + totals["external_fetch_effective_slots"],
        )
        recommended = min(global_cap, resource_limited)
        bulk_budget = max(1, recommended - min(realtime_reserve, recommended - 1))
        return {
            "configured_worker_concurrency": configured,
            "worker_global_cap": global_cap,
            "resource_limited_worker_capacity": resource_limited,
            "recommended_worker_concurrency": recommended,
            "realtime_reserved_worker_slots": min(realtime_reserve, recommended),
            "bulk_worker_budget": bulk_budget,
        }

    def _bottlenecks(
        self,
        *,
        worker_capacity: dict[str, Any],
        totals: dict[str, int],
        route_capacities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        bottlenecks: list[dict[str, Any]] = []
        if (
            worker_capacity["configured_worker_concurrency"]
            < worker_capacity["recommended_worker_concurrency"]
        ):
            bottlenecks.append(
                {
                    "kind": "worker_concurrency",
                    "severity": "warning",
                    "message": "Configured worker concurrency is lower than available resource capacity.",
                    "current": worker_capacity["configured_worker_concurrency"],
                    "recommended": worker_capacity["recommended_worker_concurrency"],
                }
            )
        if totals["ai_model_effective_slots"] == 0:
            bottlenecks.append(
                {
                    "kind": "ai_models",
                    "severity": "critical",
                    "message": "No active AI model capacity is configured.",
                }
            )
        if not any(route["agent_key"] == "catalog_extractor" for route in route_capacities):
            bottlenecks.append(
                {
                    "kind": "catalog_routes",
                    "severity": "warning",
                    "message": "No enabled catalog extractor route is available.",
                }
            )
        if totals["telegram_userbot_effective_slots"] == 0:
            bottlenecks.append(
                {
                    "kind": "telegram_userbots",
                    "severity": "warning",
                    "message": "No active Telegram userbot is available for source ingestion.",
                }
            )
        if totals["telegram_bot_effective_slots"] == 0:
            bottlenecks.append(
                {
                    "kind": "telegram_bots",
                    "severity": "warning",
                    "message": "No active Telegram bot is available for notifications.",
                }
            )
        return bottlenecks


def _totals(
    *,
    ai_model_pools: list[dict[str, Any]],
    telegram_userbot_pools: list[dict[str, Any]],
    telegram_bot_pools: list[dict[str, Any]],
    local_parser_pool: dict[str, Any],
    external_fetch_pool: dict[str, Any],
) -> dict[str, int]:
    return {
        "ai_model_effective_slots": sum(int(pool["effective_limit"]) for pool in ai_model_pools),
        "ai_model_available_slots": sum(int(pool["available_slots"]) for pool in ai_model_pools),
        "telegram_userbot_effective_slots": sum(
            int(pool["effective_limit"]) for pool in telegram_userbot_pools
        ),
        "telegram_bot_effective_slots": sum(
            int(pool["effective_limit"]) for pool in telegram_bot_pools
        ),
        "local_parser_effective_slots": int(local_parser_pool["effective_limit"]),
        "external_fetch_effective_slots": int(external_fetch_pool["effective_limit"]),
    }


def _ai_capabilities(
    model_type: str,
    *,
    endpoint_family: str | None,
    supports_structured_output: bool,
    supports_json_mode: bool,
    supports_thinking: bool,
    supports_image_input: bool,
    supports_document_input: bool,
) -> list[str]:
    capabilities_by_type = {
        "language": ["llm.text", "llm.text.fast", "llm.text.strong"],
        "ocr": ["ocr.document", "ocr.image"],
        "vision_language": ["llm.text", "vision.image", "ocr.image"],
        "image_generation": ["image.generate"],
        "video_generation": ["video.generate"],
        "realtime_audio_video": ["audio.transcribe", "video.realtime"],
    }
    capabilities = list(capabilities_by_type.get(model_type, [model_type]))
    if endpoint_family == "layout_parsing" and "document.parse" not in capabilities:
        capabilities.append("document.parse")
    if supports_structured_output or supports_json_mode:
        capabilities.append("llm.structured_output")
    if supports_thinking:
        capabilities.append("llm.thinking")
    if supports_image_input and "vision.image" not in capabilities:
        capabilities.append("vision.image")
    if supports_document_input and "document.input" not in capabilities:
        capabilities.append("document.input")
    return capabilities


def _positive_int(value: Any, *, default: int) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(default))
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return max(1, int(default))
    return max(1, parsed)


def _ratio(value: Any, *, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.01, min(1.0, parsed))


def _effective_limit(raw_limit: int, utilization_ratio: float) -> int:
    return max(1, int(raw_limit * utilization_ratio))
