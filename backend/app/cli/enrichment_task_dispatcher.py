from __future__ import annotations

import argparse
import asyncio
import logging

from app.application.enrichment.use_cases import DispatchEnrichmentTasks
from app.db.session import create_sessionmaker
from app.infrastructure.persistence.enrichment_repository import PostgresEnrichmentJobRepository
from app.infrastructure.queue.celery_publisher import CeleryEnrichmentTaskPublisher

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish pending enrichment tasks from PostgreSQL outbox")
    parser.add_argument("--once", action="store_true", help="publish one batch and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="poll interval in seconds")
    parser.add_argument("--limit", type=int, default=100, help="max tasks to claim per poll")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(once=args.once, interval=args.interval, limit=args.limit))


async def _run(*, once: bool, interval: float, limit: int) -> None:
    session_factory = create_sessionmaker()
    repository = PostgresEnrichmentJobRepository(session_factory)
    use_case = DispatchEnrichmentTasks(
        task_outbox_repository=repository,
        task_publisher=CeleryEnrichmentTaskPublisher(),
    )
    while True:
        published = await use_case.execute(limit=limit)
        if published:
            logger.info("Published %s enrichment task(s)", len(published))
        if once:
            return
        await asyncio.sleep(interval)


if __name__ == "__main__":
    main()
