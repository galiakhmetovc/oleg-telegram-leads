"""Telegram message context fetching jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from pur_leads.core.ids import new_id
from pur_leads.core.time import utc_now
from pur_leads.integrations.telegram.client import TelegramClientPort
from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    TelegramMessage,
)
from pur_leads.models.telegram_sources import (
    message_context_links_table,
    monitored_sources_table,
    source_messages_table,
)


@dataclass(frozen=True)
class MessageContextFetchResult:
    source_message_id: str
    telegram_message_id: int
    created_source_messages: int
    existing_source_messages: int
    created_links: int
    existing_links: int
    reply_ancestor_count: int
    neighbor_before_count: int
    neighbor_after_count: int


class MessageContextWorker:
    def __init__(self, session: Session, client: TelegramClientPort) -> None:
        self.session = session
        self.client = client

    async def fetch_context(
        self,
        source_message_id: str,
        *,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContextFetchResult:
        target, source = self._require_target_and_source(source_message_id)
        resolved = _resolved_source_from_row(source)
        context = await self.client.fetch_context(
            resolved,
            message_id=target["telegram_message_id"],
            before=before,
            after=after,
            reply_depth=reply_depth,
        )

        created_messages = 0
        existing_messages = 0
        created_links = 0
        existing_links = 0

        for relation_type, distance, message in _iter_related_messages(context):
            related_id, created = self._ensure_source_message(source["id"], message)
            if created:
                created_messages += 1
            else:
                existing_messages += 1

            if self._ensure_context_link(
                source_message_id=target["id"],
                related_source_message_id=related_id,
                relation_type=relation_type,
                distance=distance,
            ):
                created_links += 1
            else:
                existing_links += 1

        self.session.commit()
        return MessageContextFetchResult(
            source_message_id=target["id"],
            telegram_message_id=target["telegram_message_id"],
            created_source_messages=created_messages,
            existing_source_messages=existing_messages,
            created_links=created_links,
            existing_links=existing_links,
            reply_ancestor_count=len(context.reply_messages),
            neighbor_before_count=len(context.neighbor_before),
            neighbor_after_count=len(context.neighbor_after),
        )

    def _require_target_and_source(
        self, source_message_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        target_row = (
            self.session.execute(
                select(source_messages_table).where(source_messages_table.c.id == source_message_id)
            )
            .mappings()
            .first()
        )
        if target_row is None:
            raise KeyError(source_message_id)

        target = dict(target_row)
        source_row = (
            self.session.execute(
                select(monitored_sources_table).where(
                    monitored_sources_table.c.id == target["monitored_source_id"]
                )
            )
            .mappings()
            .first()
        )
        if source_row is None:
            raise KeyError(target["monitored_source_id"])

        source = dict(source_row)
        return target, source

    def _ensure_source_message(
        self,
        monitored_source_id: str,
        message: TelegramMessage,
    ) -> tuple[str, bool]:
        existing_id = self._source_message_id(monitored_source_id, message.telegram_message_id)
        if existing_id is not None:
            return existing_id, False

        row_id = new_id()
        now = utc_now()
        self.session.execute(
            insert(source_messages_table).values(
                id=row_id,
                monitored_source_id=monitored_source_id,
                raw_source_id=None,
                telegram_message_id=message.telegram_message_id,
                sender_id=message.sender_id,
                message_date=message.message_date,
                text=message.text,
                caption=message.caption,
                normalized_text=None,
                has_media=message.has_media,
                media_metadata_json=message.media_metadata_json,
                reply_to_message_id=message.reply_to_message_id,
                thread_id=message.thread_id,
                forward_metadata_json=message.forward_metadata_json,
                raw_metadata_json=message.raw_metadata_json,
                fetched_at=now,
                classification_status="unclassified",
                archive_pointer_id=None,
                is_archived_stub=False,
                text_archived=False,
                caption_archived=False,
                metadata_archived=False,
                created_at=now,
                updated_at=now,
            )
        )
        return row_id, True

    def _source_message_id(self, monitored_source_id: str, telegram_message_id: int) -> str | None:
        return self.session.execute(
            select(source_messages_table.c.id).where(
                source_messages_table.c.monitored_source_id == monitored_source_id,
                source_messages_table.c.telegram_message_id == telegram_message_id,
            )
        ).scalar_one_or_none()

    def _ensure_context_link(
        self,
        *,
        source_message_id: str,
        related_source_message_id: str,
        relation_type: str,
        distance: int,
    ) -> bool:
        existing_id = self.session.execute(
            select(message_context_links_table.c.id).where(
                message_context_links_table.c.source_message_id == source_message_id,
                message_context_links_table.c.related_source_message_id
                == related_source_message_id,
                message_context_links_table.c.relation_type == relation_type,
            )
        ).scalar_one_or_none()
        if existing_id is not None:
            return False

        self.session.execute(
            insert(message_context_links_table).values(
                id=new_id(),
                source_message_id=source_message_id,
                related_source_message_id=related_source_message_id,
                relation_type=relation_type,
                distance=distance,
                created_at=utc_now(),
            )
        )
        return True


def _resolved_source_from_row(source: dict[str, Any]) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=source["input_ref"],
        source_kind=source["source_kind"],
        telegram_id=source["telegram_id"],
        username=source["username"],
        title=source["title"],
    )


def _iter_related_messages(context: MessageContext) -> list[tuple[str, int, TelegramMessage]]:
    related: list[tuple[str, int, TelegramMessage]] = []
    related.extend(
        ("reply_ancestor", distance, message)
        for distance, message in enumerate(context.reply_messages, start=1)
    )
    related.extend(
        ("neighbor_before", -distance, message)
        for distance, message in enumerate(context.neighbor_before, start=1)
    )
    related.extend(
        ("neighbor_after", distance, message)
        for distance, message in enumerate(context.neighbor_after, start=1)
    )
    return related
