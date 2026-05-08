from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import timedelta

from app.application.notifications.use_cases import FlushNotificationOutbox
from app.db.session import create_sessionmaker
from app.infrastructure.notifications.telegram_sender import HttpTelegramMessageSender
from app.infrastructure.persistence.notification_outbox_repository import (
    PostgresNotificationOutboxRepository,
)
from app.infrastructure.persistence.notification_settings_repository import (
    PostgresNotificationSettingsRepository,
)

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Flush batched Telegram notification outbox")
    parser.add_argument("--once", action="store_true", help="flush once and exit")
    parser.add_argument("--interval", type=float, default=30.0, help="poll interval in seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(once=args.once, interval=args.interval))


async def _run(*, once: bool, interval: float) -> None:
    session_factory = create_sessionmaker()
    use_case = FlushNotificationOutbox(
        settings_repository=PostgresNotificationSettingsRepository(session_factory),
        outbox_repository=PostgresNotificationOutboxRepository(session_factory),
        sender=HttpTelegramMessageSender(),
        flush_interval=timedelta(minutes=5),
    )
    while True:
        sent = await use_case.execute()
        if sent:
            logger.info("Flushed %s Telegram notification batch(es)", len(sent))
        if once:
            return
        await asyncio.sleep(interval)


if __name__ == "__main__":
    main()
