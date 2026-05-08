from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def trim_enrichment_events(session: AsyncSession, *, max_rows: int) -> int:
    if max_rows < 0:
        return 0
    result = await session.execute(
        sa.text(
            """
            delete from enrichment_events
            where sequence in (
                select sequence
                from enrichment_events
                order by sequence desc
                offset :max_rows
            )
            """
        ),
        {"max_rows": max_rows},
    )
    return max(cast(Any, result).rowcount or 0, 0)


async def trim_notification_outbox(session: AsyncSession, *, max_rows: int) -> int:
    if max_rows < 0:
        return 0
    result = await session.execute(
        sa.text(
            """
            delete from notification_outbox
            where status not in ('pending', 'sending')
              and id in (
                  select id
                  from notification_outbox
                  where status not in ('pending', 'sending')
                  order by coalesce(sent_at, created_at) desc, id desc
                  offset :max_rows
              )
            """
        ),
        {"max_rows": max_rows},
    )
    return max(cast(Any, result).rowcount or 0, 0)
