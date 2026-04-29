"""Command-line entrypoint for PUR Leads."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
from collections.abc import Sequence
from pathlib import Path

from pur_leads.core.config import load_settings
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.ai.zai_client import ZaiChatCompletionClient
from pur_leads.integrations.catalog.external_page import HttpExternalPageFetcher
from pur_leads.integrations.catalog.heuristic_extractor import HeuristicCatalogExtractor
from pur_leads.integrations.catalog.llm_extractor import LlmCatalogExtractor
from pur_leads.integrations.documents.pdf_parser import PdfArtifactParser
from pur_leads.integrations.leads.fuzzy_classifier import FuzzyCatalogLeadClassifier
from pur_leads.integrations.leads.llm_shadow_classifier import LlmLeadShadowClassifier
from pur_leads.integrations.telegram.bot_notifier import TelegramBotLeadNotifier
from pur_leads.integrations.telegram.telethon_client import TelethonTelegramClient
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramDocumentDownload,
    TelegramMessage,
)
from pur_leads.services.ai_concurrency import AiModelConcurrencyService
from pur_leads.services.ai_registry import AiAgentRouteSelection, AiRegistryService
from pur_leads.services.secrets import SecretRefService
from pur_leads.services.settings import SettingsService
from pur_leads.services.userbots import UserbotAccountService
from pur_leads.workers.runtime import (
    WorkerRunResult,
    WorkerRuntime,
    build_catalog_handler_registry,
    build_lead_handler_registry,
    build_telegram_handler_registry,
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pur-leads")
    parser.add_argument("--database-path", type=Path, default=None)

    subcommands = parser.add_subparsers(required=True)

    db_parser = subcommands.add_parser("db")
    db_commands = db_parser.add_subparsers(required=True)
    db_upgrade = db_commands.add_parser("upgrade")
    db_upgrade.set_defaults(handler=_db_upgrade)

    settings_parser = subcommands.add_parser("settings")
    settings_commands = settings_parser.add_subparsers(required=True)
    settings_list = settings_commands.add_parser("list")
    settings_list.set_defaults(handler=_settings_list)
    settings_set = settings_commands.add_parser("set")
    settings_set.add_argument("key")
    settings_set.add_argument("json_value")
    settings_set.set_defaults(handler=_settings_set)

    worker_parser = subcommands.add_parser("worker")
    worker_commands = worker_parser.add_subparsers(required=True)
    worker_once = worker_commands.add_parser("once")
    worker_once.set_defaults(handler=_worker_once)
    worker_run = worker_commands.add_parser("run")
    worker_run.add_argument("--poll-interval-seconds", type=float, default=5.0)
    worker_run.add_argument("--max-iterations", type=int, default=None)
    worker_run.add_argument("--concurrency", type=int, default=None)
    worker_run.set_defaults(handler=_worker_run)

    web_parser = subcommands.add_parser("web")
    web_parser.set_defaults(handler=_web)

    return parser


def _db_upgrade(args: argparse.Namespace) -> None:
    engine = _engine_from_args(args)
    upgrade_database(engine)
    print("database upgraded")


def _settings_list(args: argparse.Namespace) -> None:
    with _session_from_args(args) as session:
        service = SettingsService(session)
        rows = service.list()
        for row in rows:
            print(f"{row.key}={json.dumps(row.value_json, ensure_ascii=False)}")


def _settings_set(args: argparse.Namespace) -> None:
    value = json.loads(args.json_value)
    with _session_from_args(args) as session:
        service = SettingsService(session)
        service.set(
            args.key,
            value,
            value_type=_infer_value_type(value),
            updated_by="cli",
            reason="cli settings set",
        )
    print(f"{args.key} updated")


def _worker_once(args: argparse.Namespace) -> None:
    _ensure_database_upgraded(args)
    result = asyncio.run(_worker_run_once(args, worker_name="cli-worker"))
    if result.status == "idle":
        print("no queued jobs")
        return
    print(f"{result.status} job {result.job_id} ({result.job_type})")


def _worker_run(args: argparse.Namespace) -> None:
    _ensure_database_upgraded(args)
    iterations = asyncio.run(_worker_run_loop(args))
    print(f"worker stopped after {iterations} iterations")


async def _worker_run_loop(args: argparse.Namespace) -> int:
    iterations = 0
    batches = 0
    while args.max_iterations is None or batches < args.max_iterations:
        concurrency = _worker_concurrency(args)
        results = await asyncio.gather(
            *(
                _worker_run_once(args, worker_name=f"cli-worker-{index + 1}")
                for index in range(concurrency)
            )
        )
        batches += 1
        iterations += len(results)
        if any(result.status != "idle" for result in results):
            for result in results:
                if result.status != "idle":
                    print(f"{result.status} job {result.job_id} ({result.job_type})")
            continue
        if args.poll_interval_seconds > 0:
            await asyncio.sleep(args.poll_interval_seconds)
    return iterations


async def _worker_run_single_loop(args: argparse.Namespace, *, worker_name: str) -> int:
    iterations = 0
    while args.max_iterations is None or iterations < args.max_iterations:
        result = await _worker_run_once(args, worker_name=worker_name)
        iterations += 1
        if result.status != "idle":
            print(f"{result.status} job {result.job_id} ({result.job_type})")
            continue
        if args.poll_interval_seconds > 0:
            await asyncio.sleep(args.poll_interval_seconds)
    return iterations


async def _worker_run_once(args: argparse.Namespace, *, worker_name: str) -> WorkerRunResult:
    with _session_from_args(args) as session:
        telegram_client = _build_telegram_client(session)
        try:
            runtime = WorkerRuntime(
                session,
                handlers=_build_worker_handlers(
                    session,
                    worker_name=worker_name,
                    telegram_client=telegram_client,
                ),
                worker_name=worker_name,
            )
            return await runtime.run_once()
        finally:
            await _close_async_resource(telegram_client)


def _worker_concurrency(args: argparse.Namespace) -> int:
    configured = args.concurrency
    if configured is None:
        try:
            with _session_from_args(args) as session:
                explicit = SettingsService(session).repository.get("worker_concurrency")
                configured = (
                    int(explicit.value_json)
                    if explicit is not None
                    else load_settings().worker_concurrency
                )
        except Exception:
            configured = load_settings().worker_concurrency
    return max(1, int(configured))


def _web(args: argparse.Namespace) -> None:
    import uvicorn

    from pur_leads.web.app import create_app

    settings = load_settings()
    app = create_app(database_path=args.database_path)
    uvicorn.run(
        app,
        host=settings.web_host,
        port=settings.web_port,
    )


def _session_from_args(args: argparse.Namespace):
    engine = _engine_from_args(args)
    return create_session_factory(engine)()


def _engine_from_args(args: argparse.Namespace):
    path = args.database_path or load_settings().database_path
    return create_sqlite_engine(path)


def _ensure_database_upgraded(args: argparse.Namespace) -> None:
    upgrade_database(_engine_from_args(args))


def _build_worker_handlers(
    session,
    *,
    worker_name: str = "cli-worker",
    telegram_client=None,  # noqa: ANN001
):
    settings = load_settings()
    handlers = {}
    handlers.update(
        build_catalog_handler_registry(
            session,
            parser=PdfArtifactParser(),
            extractor=_build_catalog_extractor(session, settings, worker_name=worker_name),
            external_page_fetcher=_build_external_page_fetcher(session),
        )
    )
    handlers.update(
        build_lead_handler_registry(
            session,
            classifier=FuzzyCatalogLeadClassifier(session),
            shadow_classifier=_build_lead_shadow_classifier(
                session,
                settings,
                worker_name=worker_name,
            ),
            notifier=_build_lead_notifier(session, settings),
        )
    )
    handlers.update(
        build_telegram_handler_registry(
            session,
            telegram_client if telegram_client is not None else _build_telegram_client(session),
            artifact_storage_path=settings.artifact_storage_path,
        )
    )
    return handlers


async def _close_async_resource(resource) -> None:  # type: ignore[no-untyped-def]
    close = getattr(resource, "aclose", None)
    if close is None:
        close = getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _build_lead_notifier(session, settings):
    bot_token = _setting_secret_or_env(
        session,
        "telegram_bot_token_secret_ref",
        settings.telegram_bot_token,
    )
    if not bot_token:
        return None
    return TelegramBotLeadNotifier(bot_token)


def _build_catalog_extractor(session, settings, *, worker_name: str):
    settings_service = SettingsService(session)
    if not bool(settings_service.get("catalog_llm_extraction_enabled")):
        return HeuristicCatalogExtractor(session)
    route = _select_ai_route(session, agent_key="catalog_extractor", route_role="primary")
    heuristic_fallback = bool(settings_service.get("catalog_llm_fallback_to_heuristic"))
    provider = str(_setting_or_route_provider(settings_service, "catalog_llm_provider", route))
    api_key = _zai_api_key_for_route(session, settings, route)
    if provider != "zai" or not api_key:
        if heuristic_fallback:
            return HeuristicCatalogExtractor(session)
        raise ValueError("catalog LLM extractor is enabled but Z.AI is not configured")

    fallback_extractor = _build_catalog_rate_limit_fallback_extractor(
        session,
        settings,
        settings_service,
        primary_route=route,
        worker_name=worker_name,
        heuristic_fallback=heuristic_fallback,
    )
    return _build_catalog_llm_extractor_for_route(
        session,
        settings,
        settings_service,
        route=route,
        worker_name=worker_name,
        allow_settings_overrides=route is None,
        fallback_extractor=fallback_extractor,
        fallback_on_rate_limit=fallback_extractor is not None,
        fallback_on_error=bool(route.fallback_on_error) if route is not None else False,
    )


def _build_catalog_rate_limit_fallback_extractor(
    session,
    settings,
    settings_service: SettingsService,
    *,
    primary_route: AiAgentRouteSelection | None,
    worker_name: str,
    heuristic_fallback: bool,
):
    route_allows_fallback = (
        primary_route.fallback_on_rate_limit if primary_route is not None else True
    )
    if not route_allows_fallback:
        return None
    if bool(settings_service.get("catalog_llm_rate_limit_fallback_enabled")):
        fallback_route = _select_ai_route(
            session,
            agent_key="catalog_extractor",
            route_role="fallback",
        )
        if fallback_route is not None:
            fallback_api_key = _zai_api_key_for_route(session, settings, fallback_route)
            if fallback_route.provider == "zai" and fallback_api_key:
                return _build_catalog_llm_extractor_for_route(
                    session,
                    settings,
                    settings_service,
                    route=fallback_route,
                    worker_name=worker_name,
                    allow_settings_overrides=False,
                )
    return HeuristicCatalogExtractor(session) if heuristic_fallback else None


def _build_catalog_llm_extractor_for_route(
    session,
    settings,
    settings_service: SettingsService,
    *,
    route: AiAgentRouteSelection | None,
    worker_name: str,
    allow_settings_overrides: bool,
    fallback_extractor=None,  # noqa: ANN001
    fallback_on_rate_limit: bool = False,
    fallback_on_error: bool = False,
):
    if allow_settings_overrides:
        base_url = str(
            _setting_or_env_or_default(
                settings_service,
                "catalog_llm_base_url",
                env_names=("PUR_CATALOG_LLM_BASE_URL", "CATALOG_LLM_BASE_URL"),
                env_value=settings.catalog_llm_base_url,
                default=route.base_url if route is not None else settings.catalog_llm_base_url,
            )
        )
        model = str(
            _setting_or_env_or_default(
                settings_service,
                "catalog_llm_model",
                env_names=("PUR_CATALOG_LLM_MODEL", "CATALOG_LLM_MODEL"),
                env_value=settings.catalog_llm_model,
                default=route.model if route is not None else settings.catalog_llm_model,
            )
        )
        temperature = float(
            _setting_or_default(
                settings_service,
                "catalog_llm_temperature",
                route.temperature if route is not None and route.temperature is not None else 0.0,
            )
        )
        max_tokens = int(
            _setting_or_default(
                settings_service,
                "catalog_llm_max_tokens",
                route.max_output_tokens if route is not None and route.max_output_tokens else 4096,
            )
        )
    else:
        if route is None:
            raise ValueError("catalog fallback route is required")
        base_url = route.base_url
        model = route.model
        temperature = float(route.temperature if route.temperature is not None else 0.0)
        max_tokens = int(route.max_output_tokens or 4096)
    api_key = _zai_api_key_for_route(session, settings, route)
    if not api_key:
        raise ValueError("catalog LLM extractor is enabled but Z.AI is not configured")
    return LlmCatalogExtractor(
        client=ZaiChatCompletionClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=_llm_request_timeout_seconds(
                settings_service,
                task_type="catalog_extraction",
                model=model,
                default=settings.catalog_llm_timeout_seconds,
            ),
            connect_timeout_seconds=_llm_connect_timeout_seconds(settings_service),
            concurrency_limiter=_build_ai_model_concurrency_limiter(
                session,
                worker_name=worker_name,
            ),
            provider_account_id=route.provider_account_id if route is not None else None,
            thinking_type=_zai_thinking_type_for_route(route),
            response_format=_zai_response_format_for_route(route),
            worker_name=worker_name,
        ),
        model=model,
        session=session,
        temperature=temperature,
        max_tokens=max_tokens,
        fallback_extractor=fallback_extractor,
        fallback_on_rate_limit=fallback_on_rate_limit,
        fallback_on_error=fallback_on_error,
    )


def _build_lead_shadow_classifier(session, settings, *, worker_name: str):
    settings_service = SettingsService(session)
    if not bool(settings_service.get("lead_llm_shadow_enabled")):
        return None
    route = _select_ai_route(session, agent_key="lead_detector", route_role="shadow")
    provider = str(_setting_or_route_provider(settings_service, "lead_llm_shadow_provider", route))
    api_key = _zai_api_key_for_route(session, settings, route)
    fallback = bool(settings_service.get("lead_llm_shadow_fallback_on_error"))
    if provider != "zai" or not api_key:
        if fallback:
            return None
        raise ValueError("lead LLM shadow classifier is enabled but Z.AI is not configured")
    base_url = str(
        _setting_or_env_or_default(
            settings_service,
            "lead_llm_shadow_base_url",
            env_names=("PUR_LEAD_LLM_SHADOW_BASE_URL", "LEAD_LLM_SHADOW_BASE_URL"),
            env_value=settings.lead_llm_shadow_base_url,
            default=route.base_url if route is not None else settings.lead_llm_shadow_base_url,
        )
    )
    model = str(
        _setting_or_env_or_default(
            settings_service,
            "lead_llm_shadow_model",
            env_names=("PUR_LEAD_LLM_SHADOW_MODEL", "LEAD_LLM_SHADOW_MODEL"),
            env_value=settings.lead_llm_shadow_model,
            default=route.model if route is not None else settings.lead_llm_shadow_model,
        )
    )
    temperature = float(
        _setting_or_default(
            settings_service,
            "lead_llm_shadow_temperature",
            route.temperature if route is not None and route.temperature is not None else 0.0,
        )
    )
    max_tokens = int(
        _setting_or_default(
            settings_service,
            "lead_llm_shadow_max_tokens",
            route.max_output_tokens if route is not None and route.max_output_tokens else 2048,
        )
    )
    return LlmLeadShadowClassifier(
        client=ZaiChatCompletionClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=_llm_request_timeout_seconds(
                settings_service,
                task_type="lead_detection",
                model=model,
                default=settings.lead_llm_shadow_timeout_seconds,
            ),
            connect_timeout_seconds=_llm_connect_timeout_seconds(settings_service),
            concurrency_limiter=_build_ai_model_concurrency_limiter(
                session,
                worker_name=worker_name,
            ),
            provider_account_id=route.provider_account_id if route is not None else None,
            thinking_type=_zai_thinking_type_for_route(route),
            response_format=_zai_response_format_for_route(route),
            worker_name=worker_name,
        ),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _build_ai_model_concurrency_limiter(session, *, worker_name: str):
    settings_service = SettingsService(session)
    if not bool(settings_service.get("ai_model_concurrency_enabled")):
        return None
    registry = AiRegistryService(session)
    configured_limits = settings_service.repository.get("ai_model_concurrency_limits")
    registry_limits = registry.model_concurrency_limits(provider_key="zai")
    limits_value = (
        configured_limits.value_json
        if configured_limits is not None
        else registry_limits or settings_service.get("ai_model_concurrency_limits")
    )
    limits = limits_value if isinstance(limits_value, dict) else None
    return AiModelConcurrencyService(
        session,
        limits=limits,
        utilization_ratio=float(
            _setting_or_default(settings_service, "ai_model_concurrency_utilization_ratio", 0.8)
        ),
        default_limit=int(
            _setting_or_default(settings_service, "ai_model_concurrency_default_limit", 1)
        ),
        lease_seconds=int(
            _setting_or_default(settings_service, "ai_model_concurrency_lease_seconds", 180)
        ),
        retry_after_seconds=int(
            _setting_or_default(settings_service, "ai_model_concurrency_retry_after_seconds", 5)
        ),
    )


def _build_external_page_fetcher(session) -> HttpExternalPageFetcher:
    settings_service = SettingsService(session)
    timeout_seconds = float(
        _setting_or_default(settings_service, "external_page_fetch_timeout_seconds", 20)
    )
    max_bytes = int(_setting_or_default(settings_service, "external_page_max_bytes", 1_048_576))
    return HttpExternalPageFetcher(timeout_seconds=timeout_seconds, max_bytes=max_bytes)


def _setting_or_default(settings_service: SettingsService, key: str, default):
    record = settings_service.repository.get(key)
    return record.value_json if record is not None else default


def _llm_connect_timeout_seconds(settings_service: SettingsService) -> float:
    return float(_setting_value_or_default(settings_service, "llm_connect_timeout_seconds", 5))


def _llm_request_timeout_seconds(
    settings_service: SettingsService,
    *,
    task_type: str,
    model: str,
    default: float,
) -> float:
    hard_cap = float(
        _setting_value_or_default(settings_service, "llm_request_timeout_hard_cap_seconds", 180)
    )
    by_model = _setting_value_or_default(
        settings_service, "llm_request_timeout_seconds_by_model", {}
    )
    by_task = _setting_value_or_default(settings_service, "llm_request_timeout_seconds_by_task", {})
    selected = _timeout_from_map(by_model, model.casefold())
    if selected is None:
        selected = _timeout_from_map(by_task, task_type.casefold())
    if selected is None:
        selected = float(default)
    return min(max(1.0, float(selected)), max(1.0, hard_cap))


def _setting_value_or_default(settings_service: SettingsService, key: str, default):
    try:
        value = settings_service.get(key)
    except Exception:
        return default
    return default if value is None else value


def _timeout_from_map(value, key: str) -> float | None:  # noqa: ANN001
    if not isinstance(value, dict):
        return None
    for raw_key, raw_value in value.items():
        if str(raw_key).casefold() != key:
            continue
        try:
            timeout = float(raw_value)
        except (TypeError, ValueError):
            return None
        return timeout if timeout > 0 else None
    return None


def _setting_or_env_or_default(
    settings_service: SettingsService,
    key: str,
    *,
    env_names: Sequence[str],
    env_value,
    default,
):
    record = settings_service.repository.get(key)
    if record is not None:
        return record.value_json
    if any(os.getenv(name) is not None for name in env_names):
        return env_value
    return default


def _setting_or_route_provider(
    settings_service: SettingsService,
    key: str,
    route: AiAgentRouteSelection | None,
) -> str:
    record = settings_service.repository.get(key)
    if record is not None:
        return str(record.value_json)
    if route is not None:
        return route.provider
    return str(settings_service.get(key) or "zai")


def _select_ai_route(
    session,
    *,
    agent_key: str,
    route_role: str,
) -> AiAgentRouteSelection | None:
    registry = AiRegistryService(session)
    routes = registry.select_routes(agent_key=agent_key, route_role=route_role)
    return routes[0] if routes else None


def _zai_thinking_type_for_route(route: AiAgentRouteSelection | None) -> str | None:
    if route is None or not route.supports_thinking:
        return None
    mode = str(route.thinking_mode or ("on" if route.thinking_enabled else "off")).casefold()
    if mode in {"off", "disabled", "none", "false", "0"}:
        return "disabled"
    return "enabled"


def _zai_response_format_for_route(route: AiAgentRouteSelection | None) -> dict[str, str] | None:
    if route is None or not route.structured_output_required:
        return None
    if not (route.supports_structured_output or route.supports_json_mode):
        return None
    return {"type": "json_object"}


def _build_telegram_client(session):
    settings_service = SettingsService(session)
    configured_api_id = settings_service.get("telegram_api_id")
    api_id = _env_int("PUR_TELEGRAM_API_ID", "TELEGRAM_API_ID")
    if api_id is None and configured_api_id is not None:
        api_id = int(configured_api_id)
    api_hash = _setting_secret_or_env(
        session,
        "telegram_api_hash_secret_ref",
        _env_str("PUR_TELEGRAM_API_HASH", "TELEGRAM_API_HASH"),
    )
    userbot = UserbotAccountService(session).select_default_userbot()
    if api_id is None or not api_hash or userbot is None:
        return _UnconfiguredTelegramClient()
    return TelethonTelegramClient(
        session_path=userbot.session_path,
        api_id=api_id,
        api_hash=api_hash,
        flood_sleep_threshold_seconds=userbot.flood_sleep_threshold_seconds,
        get_history_wait_seconds=_history_wait_seconds(session),
    )


def _history_wait_seconds(session) -> int:
    configured = _env_int(
        "PUR_TELEGRAM_GET_HISTORY_WAIT_SECONDS", "TELEGRAM_GET_HISTORY_WAIT_SECONDS"
    )
    if configured is not None:
        return configured
    value = SettingsService(session).get("telegram_get_history_wait_seconds")
    return int(value if value is not None else 1)


def _setting_secret_or_env(session, setting_key: str, fallback: str | None) -> str | None:
    try:
        return SecretRefService(session).resolve_setting_secret(setting_key) or fallback
    except (FileNotFoundError, KeyError, ValueError):
        return fallback


def _zai_api_key(session, settings) -> str | None:
    return _setting_secret_or_env(
        session,
        "zai_api_key_secret_ref",
        settings.zai_api_key or _env_str("PUR_ZAI_API_KEY", "ZAI_API_KEY"),
    )


def _zai_api_key_for_route(
    session,
    settings,
    route: AiAgentRouteSelection | None,
) -> str | None:
    if route is None or not route.auth_secret_ref:
        return _zai_api_key(session, settings)
    value = _resolve_ai_auth_secret_ref(session, route.auth_secret_ref)
    if value:
        return value
    if route.auth_secret_ref == "env:PUR_ZAI_API_KEY":
        return _zai_api_key(session, settings)
    return None


def _resolve_ai_auth_secret_ref(session, auth_secret_ref: str) -> str | None:
    ref = auth_secret_ref.strip()
    if not ref:
        return None
    try:
        if ref.startswith("secret_ref:"):
            return SecretRefService(session).resolve_value(ref.split(":", 1)[1])
        if ref.startswith("env:"):
            return _env_str(ref.split(":", 1)[1])
        return SecretRefService(session).resolve_value(ref)
    except (FileNotFoundError, KeyError, ValueError):
        return None


def _env_str(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _env_int(*names: str) -> int | None:
    value = _env_str(*names)
    return int(value) if value is not None else None


class _UnconfiguredTelegramClient:
    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        raise ValueError("telegram client is not configured")

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        raise ValueError("telegram client is not configured")

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        raise ValueError("telegram client is not configured")

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        after_date=None,
        limit: int,
    ) -> list[TelegramMessage]:
        raise ValueError("telegram client is not configured")

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        raise ValueError("telegram client is not configured")

    async def download_message_document(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
    ) -> TelegramDocumentDownload:
        raise ValueError("telegram client is not configured")


def _infer_value_type(value) -> str:  # type: ignore[no-untyped-def]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return "json"


if __name__ == "__main__":
    main()
