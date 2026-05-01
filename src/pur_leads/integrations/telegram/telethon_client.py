"""Telethon-backed Telegram client adapter."""

from __future__ import annotations

import base64
import inspect
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from telethon import TelegramClient, errors  # type: ignore[import-untyped]

from pur_leads.integrations.telegram.types import (
    MessageContext,
    ResolvedTelegramSource,
    SourceAccessResult,
    TelegramDocumentDownload,
    TelegramMediaDownload,
    TelegramMessage,
)


class TelegramClientAuthorizationError(RuntimeError):
    """Raised when a configured Telethon session is not authorized."""


class TelethonTelegramClient:
    def __init__(
        self,
        *,
        session_path: str | Path,
        api_id: int,
        api_hash: str,
        flood_sleep_threshold_seconds: int = 60,
        get_history_wait_seconds: int = 1,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.session_path = str(session_path)
        self.api_id = api_id
        self.api_hash = api_hash
        self.flood_sleep_threshold_seconds = flood_sleep_threshold_seconds
        self.get_history_wait_seconds = get_history_wait_seconds
        self.client_factory = client_factory or TelegramClient
        self._client: Any | None = None

    async def resolve_source(self, input_ref: str) -> ResolvedTelegramSource:
        client = await self._get_client()
        entity = await client.get_entity(input_ref)
        return _source_from_entity(input_ref, entity)

    async def check_access(self, source: ResolvedTelegramSource) -> SourceAccessResult:
        client = await self._get_client()
        try:
            entity = await client.get_entity(_entity_ref(source))
            resolved = _source_from_entity(source.input_ref, entity)
            latest_messages = [message async for message in client.iter_messages(entity, limit=1)]
        except errors.FloodWaitError as exc:
            return SourceAccessResult(
                status="flood_wait",
                can_read_messages=False,
                can_read_history=False,
                resolved_source=source,
                flood_wait_seconds=int(getattr(exc, "seconds", 0) or 0),
                error=str(exc),
            )
        except Exception as exc:
            return SourceAccessResult(
                status="read_error",
                can_read_messages=False,
                can_read_history=False,
                resolved_source=source,
                error=str(exc) or exc.__class__.__name__,
            )
        return SourceAccessResult(
            status="succeeded",
            can_read_messages=True,
            can_read_history=True,
            resolved_source=resolved,
            last_message_id=latest_messages[0].id if latest_messages else None,
        )

    async def fetch_preview_messages(
        self,
        source: ResolvedTelegramSource,
        *,
        limit: int,
    ) -> list[TelegramMessage]:
        client = await self._get_client()
        entity = await client.get_entity(_entity_ref(source))
        return [
            _message_from_telethon(source, message)
            async for message in client.iter_messages(entity, limit=limit)
        ]

    async def fetch_message_batch(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None,
        after_date: datetime | None = None,
        limit: int,
    ) -> list[TelegramMessage]:
        client = await self._get_client()
        entity = await client.get_entity(_entity_ref(source))
        kwargs: dict[str, Any] = {
            "limit": limit,
            "reverse": True,
            "wait_time": self.get_history_wait_seconds,
        }
        if after_message_id is not None:
            kwargs["min_id"] = after_message_id
        elif after_date is not None:
            kwargs["offset_date"] = after_date
        return [
            _message_from_telethon(source, message)
            async for message in client.iter_messages(entity, **kwargs)
        ]

    async def iter_message_batches(
        self,
        source: ResolvedTelegramSource,
        *,
        after_message_id: int | None = None,
        from_message_id: int | None = None,
        after_date: datetime | None = None,
        limit: int | None = None,
        batch_size: int = 1000,
    ) -> AsyncIterator[list[TelegramMessage]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        client = await self._get_client()
        entity = await client.get_entity(_entity_ref(source))
        kwargs: dict[str, Any] = {
            "limit": limit,
            "reverse": True,
            "wait_time": self.get_history_wait_seconds,
        }
        if after_message_id is not None:
            kwargs["min_id"] = after_message_id
        elif from_message_id is not None:
            kwargs["min_id"] = max(from_message_id - 1, 0)
        elif after_date is not None:
            kwargs["offset_date"] = after_date

        batch: list[TelegramMessage] = []
        async for message in client.iter_messages(entity, **kwargs):
            batch.append(_message_from_telethon(source, message))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    async def fetch_context(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        before: int,
        after: int,
        reply_depth: int,
    ) -> MessageContext:
        client = await self._get_client()
        entity = await client.get_entity(_entity_ref(source))
        target = await _get_message(client, entity, message_id)
        reply_messages = []
        current = target
        for _depth in range(reply_depth):
            reply_id = _reply_to_message_id(current) if current is not None else None
            if reply_id is None:
                break
            current = await _get_message(client, entity, reply_id)
            if current is None:
                break
            reply_messages.append(_message_from_telethon(source, current))

        neighbor_before = [
            _message_from_telethon(source, message)
            async for message in client.iter_messages(entity, limit=before, max_id=message_id)
        ]
        neighbor_after = [
            _message_from_telethon(source, message)
            async for message in client.iter_messages(
                entity,
                limit=after,
                min_id=message_id,
                reverse=True,
                wait_time=self.get_history_wait_seconds,
            )
        ]
        return MessageContext(
            target_message_id=message_id,
            reply_messages=reply_messages,
            neighbor_before=neighbor_before,
            neighbor_after=neighbor_after,
        )

    async def download_message_document(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
    ) -> TelegramDocumentDownload:
        client = await self._get_client()
        entity = await client.get_entity(_entity_ref(source))
        message = await _get_message(client, entity, message_id)
        if message is None:
            return TelegramDocumentDownload(
                status="skipped",
                file_name=None,
                mime_type=None,
                file_size=None,
                local_path=None,
                skip_reason="message_not_found",
            )

        document_metadata = _document_metadata(message)
        if document_metadata is None:
            return TelegramDocumentDownload(
                status="skipped",
                file_name=None,
                mime_type=None,
                file_size=None,
                local_path=None,
                skip_reason="no_document",
            )
        if document_metadata["downloadable"] is not True:
            return TelegramDocumentDownload(
                status="skipped",
                file_name=document_metadata["file_name"],
                mime_type=document_metadata["mime_type"],
                file_size=document_metadata["file_size"],
                local_path=None,
                skip_reason=document_metadata["skip_reason"] or "not_downloadable",
            )

        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        downloaded_path = await client.download_media(message, file=str(destination))
        if downloaded_path is None:
            return TelegramDocumentDownload(
                status="failed",
                file_name=document_metadata["file_name"],
                mime_type=document_metadata["mime_type"],
                file_size=document_metadata["file_size"],
                local_path=None,
                error="download_media returned no path",
            )
        return TelegramDocumentDownload(
            status="downloaded",
            file_name=document_metadata["file_name"],
            mime_type=document_metadata["mime_type"],
            file_size=document_metadata["file_size"],
            local_path=str(downloaded_path),
        )

    async def download_message_media(
        self,
        source: ResolvedTelegramSource,
        *,
        message_id: int,
        destination_dir: str | Path,
        allowed_media_types: Sequence[str],
        max_file_size_bytes: int | None,
    ) -> TelegramMediaDownload:
        client = await self._get_client()
        entity = await client.get_entity(_entity_ref(source))
        message = await _get_message(client, entity, message_id)
        if message is None:
            return TelegramMediaDownload(
                status="skipped",
                media_type=None,
                file_name=None,
                mime_type=None,
                file_size=None,
                local_path=None,
                skip_reason="message_not_found",
            )

        metadata = _downloadable_media_metadata(message)
        if metadata is None:
            return TelegramMediaDownload(
                status="skipped",
                media_type=None,
                file_name=None,
                mime_type=None,
                file_size=None,
                local_path=None,
                skip_reason="no_media",
            )
        media_type = str(metadata["media_type"])
        if media_type not in set(allowed_media_types):
            return TelegramMediaDownload(
                status="skipped",
                media_type=media_type,
                file_name=metadata["file_name"],
                mime_type=metadata["mime_type"],
                file_size=metadata["file_size"],
                local_path=None,
                skip_reason="media_type_not_allowed",
            )
        file_size = metadata["file_size"]
        if (
            max_file_size_bytes is not None
            and file_size is not None
            and int(file_size) > max_file_size_bytes
        ):
            return TelegramMediaDownload(
                status="skipped",
                media_type=media_type,
                file_name=metadata["file_name"],
                mime_type=metadata["mime_type"],
                file_size=file_size,
                local_path=None,
                skip_reason="file_too_large",
            )

        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        downloaded_path = await client.download_media(message, file=str(destination))
        if downloaded_path is None:
            return TelegramMediaDownload(
                status="failed",
                media_type=media_type,
                file_name=metadata["file_name"],
                mime_type=metadata["mime_type"],
                file_size=file_size,
                local_path=None,
                error="download_media returned no path",
            )
        return TelegramMediaDownload(
            status="downloaded",
            media_type=media_type,
            file_name=metadata["file_name"],
            mime_type=metadata["mime_type"],
            file_size=file_size,
            local_path=str(downloaded_path),
        )

    async def _get_client(self) -> Any:
        if self._client is None:
            client = self.client_factory(
                self.session_path,
                self.api_id,
                self.api_hash,
                flood_sleep_threshold=self.flood_sleep_threshold_seconds,
            )
            await _maybe_await(client.connect())
            if not await _maybe_await(client.is_user_authorized()):
                raise TelegramClientAuthorizationError("telegram session is not authorized")
            self._client = client
        return self._client

    async def aclose(self) -> None:
        if self._client is None:
            return
        client = self._client
        self._client = None
        if hasattr(client, "disconnect"):
            await _maybe_await(client.disconnect())


async def _get_message(client: Any, entity: Any, message_id: int) -> Any | None:
    if hasattr(client, "get_messages"):
        message = await client.get_messages(entity, ids=message_id)
        if isinstance(message, list):
            return message[0] if message else None
        return message
    rows = [
        message async for message in client.iter_messages(entity, limit=1, min_id=message_id - 1)
    ]
    return rows[0] if rows else None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _source_from_entity(input_ref: str, entity: Any) -> ResolvedTelegramSource:
    return ResolvedTelegramSource(
        input_ref=input_ref,
        source_kind=_source_kind(entity),
        telegram_id=str(getattr(entity, "id", "")) or None,
        username=getattr(entity, "username", None),
        title=getattr(entity, "title", None) or _sender_display(entity),
    )


def _source_kind(entity: Any) -> str:
    if getattr(entity, "broadcast", False):
        return "telegram_channel"
    if getattr(entity, "megagroup", False):
        return "telegram_supergroup"
    if getattr(entity, "bot", False) or getattr(entity, "first_name", None):
        return "telegram_dm"
    return "telegram_group"


def _entity_ref(source: ResolvedTelegramSource) -> str:
    return source.username or source.telegram_id or source.input_ref


def _message_from_telethon(source: ResolvedTelegramSource, message: Any) -> TelegramMessage:
    text_value = _blank_to_none(getattr(message, "message", None))
    has_media = getattr(message, "media", None) is not None
    return TelegramMessage(
        monitored_source_ref=source.input_ref,
        telegram_message_id=int(message.id),
        message_date=message.date,
        sender_id=_string_or_none(getattr(message, "sender_id", None)),
        sender_display=_sender_display(getattr(message, "sender", None)),
        text=None if has_media else text_value,
        caption=text_value if has_media else None,
        has_media=has_media,
        media_metadata_json=_media_metadata(message) if has_media else None,
        reply_to_message_id=_reply_to_message_id(message),
        thread_id=_string_or_none(getattr(message, "grouped_id", None)),
        forward_metadata_json=_forward_metadata(message),
        raw_metadata_json=_raw_message_metadata(message),
    )


def _raw_message_metadata(message: Any) -> dict[str, Any]:
    return {
        "post": bool(getattr(message, "post", False)),
        "views": _json_safe(getattr(message, "views", None)),
        "forwards": _json_safe(getattr(message, "forwards", None)),
        "edit_date": _json_safe(getattr(message, "edit_date", None)),
        "grouped_id": _json_safe(getattr(message, "grouped_id", None)),
        "telethon": {
            "message": _telethon_dump(message),
            "sender": _telethon_dump(getattr(message, "sender", None)),
            "chat": _telethon_dump(getattr(message, "chat", None)),
            "media": _telethon_dump(getattr(message, "media", None)),
            "document": _telethon_dump(getattr(message, "document", None)),
            "reply_to": _telethon_dump(getattr(message, "reply_to", None)),
            "fwd_from": _telethon_dump(getattr(message, "fwd_from", None)),
            "action": _telethon_dump(getattr(message, "action", None)),
            "reactions": _telethon_dump(getattr(message, "reactions", None)),
            "entities": _telethon_dump(getattr(message, "entities", None)),
            "buttons": _telethon_dump(getattr(message, "buttons", None)),
            "via_bot": _telethon_dump(getattr(message, "via_bot", None)),
        },
    }


def _sender_display(sender: Any) -> str | None:
    if sender is None:
        return None
    title = getattr(sender, "title", None)
    if title:
        return str(title)
    username = getattr(sender, "username", None)
    first_name = getattr(sender, "first_name", None)
    last_name = getattr(sender, "last_name", None)
    name = " ".join(str(part) for part in (first_name, last_name) if part)
    return name or (str(username) if username else None)


def _media_metadata(message: Any) -> dict[str, Any]:
    media = getattr(message, "media", None)
    if media is None:
        return {}
    metadata: dict[str, Any] = {"type": media.__class__.__name__}
    document_metadata = _document_metadata(message)
    if document_metadata is not None:
        metadata["document"] = document_metadata
    return metadata


def _document_metadata(message: Any) -> dict[str, Any] | None:
    document = getattr(message, "document", None)
    if document is None:
        return None
    mime_type = _blank_to_none(getattr(document, "mime_type", None))
    skip_reason = _document_media_skip_reason(document, mime_type)
    return {
        "file_name": _document_file_name(document),
        "mime_type": mime_type,
        "file_size": _int_or_none(getattr(document, "size", None)),
        "downloadable": skip_reason is None,
        "skip_reason": skip_reason,
    }


def _document_file_name(document: Any) -> str | None:
    for attribute in getattr(document, "attributes", []) or []:
        file_name = _blank_to_none(getattr(attribute, "file_name", None))
        if file_name:
            return file_name
    return None


def _document_media_skip_reason(document: Any, mime_type: str | None) -> str | None:
    if mime_type and mime_type.startswith("video/"):
        return "video"
    if mime_type and mime_type.startswith("audio/"):
        return "audio"
    for attribute in getattr(document, "attributes", []) or []:
        attribute_name = attribute.__class__.__name__
        if attribute_name == "DocumentAttributeVideo":
            return "video"
        if attribute_name == "DocumentAttributeAudio":
            return "audio"
    return None


def _downloadable_media_metadata(message: Any) -> dict[str, Any] | None:
    media = getattr(message, "media", None)
    document = getattr(message, "document", None)
    if media is None and document is None:
        return None
    mime_type = _blank_to_none(getattr(document, "mime_type", None)) if document else None
    return {
        "media_type": _download_media_type(message, mime_type),
        "file_name": _document_file_name(document) if document else None,
        "mime_type": mime_type,
        "file_size": _int_or_none(getattr(document, "size", None)) if document else None,
    }


def _download_media_type(message: Any, mime_type: str | None) -> str:
    if mime_type:
        if mime_type.startswith("image/"):
            return "photo"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        return "document"
    media = getattr(message, "media", None)
    media_name = media.__class__.__name__.lower() if media is not None else ""
    if "photo" in media_name:
        return "photo"
    if "video" in media_name:
        return "video"
    if "audio" in media_name:
        return "audio"
    if getattr(message, "document", None) is not None:
        return "document"
    return "other"


def _forward_metadata(message: Any) -> dict[str, Any] | None:
    forward = getattr(message, "fwd_from", None)
    if forward is None:
        return None
    return {"type": forward.__class__.__name__}


def _reply_to_message_id(message: Any) -> int | None:
    reply_to_msg_id = getattr(message, "reply_to_msg_id", None)
    if reply_to_msg_id is not None:
        return int(reply_to_msg_id)
    reply_to = getattr(message, "reply_to", None)
    reply_to_msg_id = getattr(reply_to, "reply_to_msg_id", None)
    return int(reply_to_msg_id) if reply_to_msg_id is not None else None


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def _telethon_dump(value: Any) -> Any:
    return _json_safe(value, visited=set())


def _json_safe(value: Any, *, visited: set[int] | None = None, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes | bytearray | memoryview):
        return {
            "__type": "bytes",
            "encoding": "base64",
            "data": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if depth > 8:
        return repr(value)
    if visited is None:
        visited = set()
    value_id = id(value)
    if value_id in visited:
        return {"__type": value.__class__.__name__, "__cycle__": True}
    if isinstance(value, dict):
        visited.add(value_id)
        return {
            str(key): _json_safe(item, visited=visited, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        visited.add(value_id)
        return [_json_safe(item, visited=visited, depth=depth + 1) for item in value]

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        visited.add(value_id)
        try:
            dumped = to_dict()
        except Exception:
            dumped = None
        if dumped is not None:
            return _json_safe(dumped, visited=visited, depth=depth + 1)

    try:
        attributes = vars(value)
    except TypeError:
        return repr(value)
    visited.add(value_id)
    payload: dict[str, Any] = {"__class__": value.__class__.__name__}
    for key, item in attributes.items():
        if key.startswith("_"):
            continue
        payload[key] = _json_safe(item, visited=visited, depth=depth + 1)
    return payload
