from __future__ import annotations

import argparse
import asyncio
import logging

from app.application.enrichment.use_cases import CreateEnrichmentJob
from app.application.telegram_ingestion.live_service import PollTelegramSources, WatchTelegramSources
from app.application.telegram_ingestion.use_cases import IngestTelegramMessage
from app.db.session import create_sessionmaker
from app.domain.telegram_ingestion import TelegramUserbotFloodWait
from app.infrastructure.persistence.enrichment_repository import PostgresEnrichmentJobRepository
from app.infrastructure.persistence.telegram_ingestion_repository import (
    PostgresTelegramIngestionRepository,
)
from app.infrastructure.queue.celery_publisher import CeleryEnrichmentTaskPublisher
from app.infrastructure.telegram.userbot_history import TelethonUserbotHistoryClientFactory

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run configured Telegram userbot sources")
    parser.add_argument(
        "--mode",
        choices=["listen", "poll"],
        default="listen",
        help="listen uses Telegram updates; poll keeps legacy history polling",
    )
    parser.add_argument("--once", action="store_true", help="run one legacy recovery poll and exit")
    parser.add_argument("--interval", type=float, default=20.0, help="legacy poll interval in seconds")
    parser.add_argument("--batch-limit", type=int, default=100, help="messages per source recovery batch")
    parser.add_argument(
        "--cooldown-recovery-limit",
        type=int,
        default=10,
        help="messages per source while resuming immediately after FloodWait cooldown",
    )
    parser.add_argument(
        "--cooldown-recovery-delay",
        type=float,
        default=15.0,
        help="delay between source recovery reads after FloodWait cooldown",
    )
    parser.add_argument(
        "--idle-retry",
        type=float,
        default=60.0,
        help="sleep before reconnecting the live listener after a normal disconnect",
    )
    parser.add_argument(
        "--settings-reload-interval",
        type=float,
        default=600.0,
        help="seconds before reconnecting the live listener to reload Telegram source settings",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(
        _run(
            mode=args.mode,
            once=args.once,
            interval=args.interval,
            batch_limit=args.batch_limit,
            cooldown_recovery_limit=args.cooldown_recovery_limit,
            cooldown_recovery_delay=args.cooldown_recovery_delay,
            settings_reload_interval=args.settings_reload_interval,
            idle_retry=args.idle_retry,
        )
    )


async def _run(
    *,
    mode: str,
    once: bool,
    interval: float,
    batch_limit: int,
    cooldown_recovery_limit: int,
    cooldown_recovery_delay: float,
    settings_reload_interval: float,
    idle_retry: float,
) -> None:
    session_factory = create_sessionmaker()
    telegram_repository = PostgresTelegramIngestionRepository(session_factory)
    enrichment_repository = PostgresEnrichmentJobRepository(session_factory)
    ingester = IngestTelegramMessage(
        repository=telegram_repository,
        job_creator=CreateEnrichmentJob(
            repository=enrichment_repository,
            task_publisher=CeleryEnrichmentTaskPublisher(),
            task_outbox_repository=enrichment_repository,
        ),
    )
    history_client_factory = TelethonUserbotHistoryClientFactory()
    poller = PollTelegramSources(
        repository=telegram_repository,
        ingester=ingester,
        history_client_factory=history_client_factory,
        batch_limit=batch_limit,
    )
    watcher = WatchTelegramSources(
        repository=telegram_repository,
        ingester=ingester,
        history_client_factory=history_client_factory,
        recovery_limit=batch_limit,
        cooldown_recovery_limit=cooldown_recovery_limit,
        cooldown_recovery_delay_seconds=cooldown_recovery_delay,
        settings_reload_interval_seconds=settings_reload_interval,
    )
    while True:
        try:
            summary = await (watcher.execute() if mode == "listen" and not once else poller.execute())
            if summary.messages_created or summary.duplicates or summary.skipped:
                logger.info("Telegram userbot summary: %s", summary)
        except TelegramUserbotFloodWait as exc:
            logger.warning("Telegram FloodWait, sleeping %s seconds", exc.seconds)
            await asyncio.sleep(max(exc.seconds, interval))
            if once:
                return
            continue
        except Exception:
            logger.exception("Telegram userbot crashed, reconnecting after %s seconds", idle_retry)
            await asyncio.sleep(idle_retry)
            if once:
                return
            continue
        if once:
            return
        if mode == "poll":
            await asyncio.sleep(interval)
        elif summary.accounts == 0:
            logger.info("No ready Telegram userbot accounts, retrying after %s seconds", idle_retry)
            await asyncio.sleep(idle_retry)
        else:
            logger.info("Telegram live listener disconnected, reconnecting after %s seconds", idle_retry)
            await asyncio.sleep(idle_retry)


if __name__ == "__main__":
    main()
