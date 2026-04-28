"""Command-line entrypoint for PUR Leads."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path

from pur_leads.core.config import load_settings
from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database
from pur_leads.db.session import create_session_factory
from pur_leads.integrations.telegram.telethon_client import TelethonTelegramClient
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramDocumentDownload,
    TelegramMessage,
)
from pur_leads.services.settings import SettingsService
from pur_leads.services.userbots import UserbotAccountService
from pur_leads.workers.runtime import (
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
    with _session_from_args(args) as session:
        handlers = _build_worker_handlers(session)
        runtime = WorkerRuntime(session, handlers=handlers, worker_name="cli-worker")
        result = asyncio.run(runtime.run_once())
        if result.status == "idle":
            print("no queued jobs")
            return
        print(f"{result.status} job {result.job_id} ({result.job_type})")


def _worker_run(args: argparse.Namespace) -> None:
    iterations = asyncio.run(_worker_run_loop(args))
    print(f"worker stopped after {iterations} iterations")


async def _worker_run_loop(args: argparse.Namespace) -> int:
    iterations = 0
    with _session_from_args(args) as session:
        runtime = WorkerRuntime(
            session,
            handlers=_build_worker_handlers(session),
            worker_name="cli-worker",
        )
        while args.max_iterations is None or iterations < args.max_iterations:
            result = await runtime.run_once()
            iterations += 1
            if result.status != "idle":
                print(f"{result.status} job {result.job_id} ({result.job_type})")
                continue
            if args.poll_interval_seconds > 0:
                await asyncio.sleep(args.poll_interval_seconds)
    return iterations


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


def _build_worker_handlers(session):
    handlers = {}
    handlers.update(build_catalog_handler_registry(session))
    handlers.update(build_lead_handler_registry(session))
    handlers.update(build_telegram_handler_registry(session, _build_telegram_client(session)))
    return handlers


def _build_telegram_client(session):
    api_id = _env_int("PUR_TELEGRAM_API_ID", "TELEGRAM_API_ID")
    api_hash = _env_str("PUR_TELEGRAM_API_HASH", "TELEGRAM_API_HASH")
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
