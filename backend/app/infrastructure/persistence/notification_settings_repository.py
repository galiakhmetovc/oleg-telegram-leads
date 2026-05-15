from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.notifications import NotificationRoute, NotificationRouteConditions
from app.domain.notifications import NotificationSettings, TelegramBot, TelegramChat
from app.infrastructure.persistence.tables import notification_settings

NOTIFICATION_SETTINGS_CHANNEL = "telegram_routing"


class PostgresNotificationSettingsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_settings(self) -> NotificationSettings:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.select(notification_settings).where(
                    notification_settings.c.channel == NOTIFICATION_SETTINGS_CHANNEL
                )
            )
            row = result.mappings().first()
            if row is None:
                return NotificationSettings(bots=[], chats=[], routes=[], updated_at=None)
            return _settings_from_row(row)

    async def save_settings(
        self,
        settings: NotificationSettings,
    ) -> NotificationSettings:
        updated_at = datetime.now(UTC)
        config = {
            "bots": [_bot_to_dict(bot) for bot in settings.bots],
            "chats": [_chat_to_dict(chat) for chat in settings.chats],
            "routes": [_route_to_dict(route) for route in settings.routes],
        }
        statement = (
            insert(notification_settings)
            .values(channel=NOTIFICATION_SETTINGS_CHANNEL, config=config, updated_at=updated_at)
            .on_conflict_do_update(
                index_elements=[notification_settings.c.channel],
                set_={"config": config, "updated_at": updated_at},
            )
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()

        return NotificationSettings(
            bots=settings.bots,
            chats=settings.chats,
            routes=settings.routes,
            updated_at=updated_at,
        )


def _settings_from_row(row: Any) -> NotificationSettings:
    config = row["config"] or {}
    return NotificationSettings(
        bots=[_bot_from_dict(item) for item in config.get("bots", [])],
        chats=[_chat_from_dict(item) for item in config.get("chats", [])],
        routes=[_route_from_dict(item) for item in config.get("routes", [])],
        updated_at=row["updated_at"],
    )


def _bot_from_dict(data: dict[str, Any]) -> TelegramBot:
    return TelegramBot(
        id=str(data["id"]),
        name=str(data["name"]),
        enabled=bool(data.get("enabled", True)),
        token=str(data["token"]) if data.get("token") else None,
    )


def _chat_from_dict(data: dict[str, Any]) -> TelegramChat:
    return TelegramChat(
        id=str(data["id"]),
        name=str(data["name"]),
        enabled=bool(data.get("enabled", True)),
        telegram_chat_id=str(data["telegram_chat_id"]),
    )


def _route_from_dict(data: dict[str, Any]) -> NotificationRoute:
    return NotificationRoute(
        id=str(data["id"]),
        name=str(data["name"]),
        enabled=bool(data.get("enabled", True)),
        priority=int(data.get("priority", 0)),
        bot_id=str(data["bot_id"]),
        chat_id=str(data["chat_id"]),
        match_mode="any" if data.get("match_mode") == "any" else "all",
        delivery_mode="interactive" if data.get("delivery_mode") == "interactive" else "batched",
        conditions=_conditions_from_dict(data.get("conditions") or {}),
        message_template=str(data.get("message_template", "")),
    )


def _conditions_from_dict(data: dict[str, Any]) -> NotificationRouteConditions:
    return NotificationRouteConditions(
        is_lead=data.get("is_lead") if isinstance(data.get("is_lead"), bool) else None,
        score_min=_optional_int(data.get("score_min")),
        score_max=_optional_int(data.get("score_max")),
        temperatures=_str_list(data.get("temperatures")),
        review_lanes=_str_list(data.get("review_lanes")),
        solution_areas=_str_list(data.get("solution_areas")),
        customer_segments=_str_list(data.get("customer_segments")),
        domain_signals=_str_list(data.get("domain_signals")),
        facts=_str_list(data.get("facts")),
        reasons=_str_list(data.get("reasons")),
        noise_signals=_str_list(data.get("noise_signals")),
    )


def _bot_to_dict(bot: TelegramBot) -> dict[str, Any]:
    return {
        "id": bot.id,
        "name": bot.name,
        "enabled": bot.enabled,
        "token": bot.token,
    }


def _chat_to_dict(chat: TelegramChat) -> dict[str, Any]:
    return {
        "id": chat.id,
        "name": chat.name,
        "enabled": chat.enabled,
        "telegram_chat_id": chat.telegram_chat_id,
    }


def _route_to_dict(route: NotificationRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "name": route.name,
        "enabled": route.enabled,
        "priority": route.priority,
        "bot_id": route.bot_id,
        "chat_id": route.chat_id,
        "match_mode": route.match_mode,
        "delivery_mode": route.delivery_mode,
        "conditions": _conditions_to_dict(route.conditions),
        "message_template": route.message_template,
    }


def _conditions_to_dict(conditions: NotificationRouteConditions) -> dict[str, Any]:
    return {
        "is_lead": conditions.is_lead,
        "score_min": conditions.score_min,
        "score_max": conditions.score_max,
        "temperatures": conditions.temperatures,
        "review_lanes": conditions.review_lanes,
        "solution_areas": conditions.solution_areas,
        "customer_segments": conditions.customer_segments,
        "domain_signals": conditions.domain_signals,
        "facts": conditions.facts,
        "reasons": conditions.reasons,
        "noise_signals": conditions.noise_signals,
    }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
