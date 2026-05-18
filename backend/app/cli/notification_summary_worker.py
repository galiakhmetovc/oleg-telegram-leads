from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Protocol

from app.application.notifications.summary import SendNotificationSummary
from app.db.session import create_sessionmaker
from app.infrastructure.notifications.telegram_sender import HttpTelegramMessageSender
from app.infrastructure.persistence.notification_settings_repository import (
    PostgresNotificationSettingsRepository,
)
from app.infrastructure.persistence.notification_summary_repository import (
    PostgresNotificationSummaryRepository,
)

logger = logging.getLogger(__name__)


class SummaryUseCase(Protocol):
    async def execute(self) -> object: ...


def main() -> None:
    parser = argparse.ArgumentParser(description="Send day/night Telegram operational summaries")
    parser.add_argument("--once", action="store_true", help="send once and exit")
    parser.add_argument("--interval", type=float, default=60.0, help="poll interval in seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    asyncio.run(_run(once=args.once, interval=args.interval))


async def _run(*, once: bool, interval: float) -> None:
    use_case = _build_use_case()
    while True:
        result = await use_case.execute()
        if result is not None:
            logger.info("Sent Telegram notification summary")
        if once:
            return
        await asyncio.sleep(interval)


def _build_use_case() -> SendNotificationSummary:
    session_factory = create_sessionmaker()
    return SendNotificationSummary(
        settings_repository=PostgresNotificationSettingsRepository(session_factory),
        summary_repository=PostgresNotificationSummaryRepository(session_factory),
        sender=HttpTelegramMessageSender(),
    )


if __name__ == "__main__":
    main()
