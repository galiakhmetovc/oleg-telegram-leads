from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.application.notifications.use_cases import SendTelegramChatTestNotification
from app.application.notifications.use_cases import TestTelegramBot, UpdateNotificationSettings
from app.db.session import create_sessionmaker
from app.domain.notifications import NotificationRoute, NotificationRouteConditions
from app.domain.notifications import NotificationSettings, NotificationSummarySettings
from app.domain.notifications import TelegramBot, TelegramChat
from app.infrastructure.notifications.telegram_sender import HttpTelegramMessageSender, TelegramSendError
from app.infrastructure.persistence.notification_settings_repository import (
    PostgresNotificationSettingsRepository,
)

router = APIRouter(prefix="/settings/notifications", tags=["settings"])


class TelegramBotSnapshot(BaseModel):
    id: str
    name: str
    enabled: bool
    has_token: bool
    token_masked: str | None


class TelegramChatSnapshot(BaseModel):
    id: str
    name: str
    enabled: bool
    telegram_chat_id: str


class NotificationRouteConditionsSnapshot(BaseModel):
    is_lead: bool | None = None
    score_min: int | None = None
    score_max: int | None = None
    temperatures: list[str] = Field(default_factory=list)
    review_lanes: list[str] = Field(default_factory=list)
    solution_areas: list[str] = Field(default_factory=list)
    customer_segments: list[str] = Field(default_factory=list)
    domain_signals: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    noise_signals: list[str] = Field(default_factory=list)


class NotificationRouteSnapshot(BaseModel):
    id: str
    name: str
    enabled: bool
    priority: int
    bot_id: str
    chat_id: str
    match_mode: Literal["all", "any"]
    delivery_mode: Literal["batched", "interactive"] = "batched"
    conditions: NotificationRouteConditionsSnapshot
    message_template: str


class NotificationSummarySettingsSnapshot(BaseModel):
    enabled: bool
    bot_id: str
    chat_id: str
    timezone: str = "Europe/Moscow"
    day_start_hour: int = 9
    night_start_hour: int = 21


class NotificationSettingsSnapshot(BaseModel):
    bots: list[TelegramBotSnapshot]
    chats: list[TelegramChatSnapshot]
    routes: list[NotificationRouteSnapshot]
    updated_at: datetime | None
    summary: NotificationSummarySettingsSnapshot | None = None


class TelegramBotUpdate(BaseModel):
    id: str
    name: str
    enabled: bool = True
    token: str | None = None


class TelegramChatUpdate(BaseModel):
    id: str
    name: str
    enabled: bool = True
    telegram_chat_id: str


class NotificationRouteConditionsUpdate(NotificationRouteConditionsSnapshot):
    pass


class NotificationRouteUpdate(BaseModel):
    id: str
    name: str
    enabled: bool = True
    priority: int = 0
    bot_id: str
    chat_id: str
    match_mode: Literal["all", "any"] = "all"
    delivery_mode: Literal["batched", "interactive"] = "batched"
    conditions: NotificationRouteConditionsUpdate = Field(default_factory=NotificationRouteConditionsUpdate)
    message_template: str = ""


class NotificationSummarySettingsUpdate(BaseModel):
    enabled: bool = False
    bot_id: str
    chat_id: str
    timezone: str = "Europe/Moscow"
    day_start_hour: int = Field(default=9, ge=0, le=23)
    night_start_hour: int = Field(default=21, ge=0, le=23)


class NotificationSettingsUpdate(BaseModel):
    bots: list[TelegramBotUpdate] = Field(default_factory=list)
    chats: list[TelegramChatUpdate] = Field(default_factory=list)
    routes: list[NotificationRouteUpdate] = Field(default_factory=list)
    summary: NotificationSummarySettingsUpdate | None = None


class TelegramBotTestResponse(BaseModel):
    ok: bool
    message: str
    username: str


class TelegramChatTestRequest(BaseModel):
    bot_id: str
    message: str | None = None


class TelegramTestMessageResponse(BaseModel):
    ok: bool
    message: str
    telegram_message_id: int
    chat_id: str


def get_notification_settings_repository() -> PostgresNotificationSettingsRepository:
    return PostgresNotificationSettingsRepository(create_sessionmaker())


def get_telegram_message_sender() -> HttpTelegramMessageSender:
    return HttpTelegramMessageSender()


@router.get("", response_model=NotificationSettingsSnapshot)
async def get_notification_settings(
    repository: PostgresNotificationSettingsRepository = Depends(get_notification_settings_repository),
) -> NotificationSettingsSnapshot:
    return notification_settings_snapshot(await repository.get_settings())


@router.put("", response_model=NotificationSettingsSnapshot)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    repository: PostgresNotificationSettingsRepository = Depends(get_notification_settings_repository),
) -> NotificationSettingsSnapshot:
    try:
        settings = await UpdateNotificationSettings(repository).execute(settings_from_update(payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return notification_settings_snapshot(settings)


@router.post("/telegram/bots/{bot_id}/test", response_model=TelegramBotTestResponse)
async def test_telegram_bot(
    bot_id: str,
    repository: PostgresNotificationSettingsRepository = Depends(get_notification_settings_repository),
    sender: HttpTelegramMessageSender = Depends(get_telegram_message_sender),
) -> TelegramBotTestResponse:
    try:
        result = await TestTelegramBot(repository, sender).execute(bot_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TelegramSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TelegramBotTestResponse(
        ok=True,
        message="Telegram bot token is valid",
        username=result.username,
    )


@router.post("/telegram/chats/{chat_id}/test", response_model=TelegramTestMessageResponse)
async def send_telegram_chat_test_message(
    chat_id: str,
    payload: TelegramChatTestRequest,
    repository: PostgresNotificationSettingsRepository = Depends(get_notification_settings_repository),
    sender: HttpTelegramMessageSender = Depends(get_telegram_message_sender),
) -> TelegramTestMessageResponse:
    try:
        result = await SendTelegramChatTestNotification(repository, sender).execute(
            bot_id=payload.bot_id,
            chat_id=chat_id,
            message=payload.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TelegramSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TelegramTestMessageResponse(
        ok=True,
        message="Тестовое сообщение отправлено",
        telegram_message_id=result.message_id,
        chat_id=result.chat_id,
    )


async def read_notification_settings_snapshot(
    repository: PostgresNotificationSettingsRepository,
) -> NotificationSettingsSnapshot:
    return notification_settings_snapshot(await repository.get_settings())


def settings_from_update(payload: NotificationSettingsUpdate) -> NotificationSettings:
    return NotificationSettings(
        bots=[
            TelegramBot(
                id=item.id,
                name=item.name,
                enabled=item.enabled,
                token=item.token,
            )
            for item in payload.bots
        ],
        chats=[
            TelegramChat(
                id=item.id,
                name=item.name,
                enabled=item.enabled,
                telegram_chat_id=item.telegram_chat_id,
            )
            for item in payload.chats
        ],
        routes=[
            NotificationRoute(
                id=item.id,
                name=item.name,
                enabled=item.enabled,
                priority=item.priority,
                bot_id=item.bot_id,
                chat_id=item.chat_id,
                match_mode=item.match_mode,
                delivery_mode=item.delivery_mode,
                conditions=conditions_from_update(item.conditions),
                message_template=item.message_template,
            )
            for item in payload.routes
        ],
        updated_at=None,
        summary=summary_from_update(payload.summary),
    )


def conditions_from_update(payload: NotificationRouteConditionsUpdate) -> NotificationRouteConditions:
    return NotificationRouteConditions(
        is_lead=payload.is_lead,
        score_min=payload.score_min,
        score_max=payload.score_max,
        temperatures=payload.temperatures,
        review_lanes=payload.review_lanes,
        solution_areas=payload.solution_areas,
        customer_segments=payload.customer_segments,
        domain_signals=payload.domain_signals,
        facts=payload.facts,
        reasons=payload.reasons,
        noise_signals=payload.noise_signals,
    )


def summary_from_update(
    payload: NotificationSummarySettingsUpdate | None,
) -> NotificationSummarySettings | None:
    if payload is None:
        return None
    return NotificationSummarySettings(
        enabled=payload.enabled,
        bot_id=payload.bot_id,
        chat_id=payload.chat_id,
        timezone=payload.timezone,
        day_start_hour=payload.day_start_hour,
        night_start_hour=payload.night_start_hour,
    )


def notification_settings_snapshot(settings: NotificationSettings) -> NotificationSettingsSnapshot:
    return NotificationSettingsSnapshot(
        bots=[bot_snapshot(bot) for bot in settings.bots],
        chats=[
            TelegramChatSnapshot(
                id=chat.id,
                name=chat.name,
                enabled=chat.enabled,
                telegram_chat_id=chat.telegram_chat_id,
            )
            for chat in settings.chats
        ],
        routes=[route_snapshot(route) for route in settings.routes],
        updated_at=settings.updated_at,
        summary=summary_snapshot(settings.summary),
    )


def bot_snapshot(bot: TelegramBot) -> TelegramBotSnapshot:
    return TelegramBotSnapshot(
        id=bot.id,
        name=bot.name,
        enabled=bot.enabled,
        has_token=bot.has_token,
        token_masked=mask_bot_token(bot.token),
    )


def route_snapshot(route: NotificationRoute) -> NotificationRouteSnapshot:
    return NotificationRouteSnapshot(
        id=route.id,
        name=route.name,
        enabled=route.enabled,
        priority=route.priority,
        bot_id=route.bot_id,
        chat_id=route.chat_id,
        match_mode=route.match_mode,
        delivery_mode=route.delivery_mode,
        conditions=NotificationRouteConditionsSnapshot(**route.conditions.__dict__),
        message_template=route.message_template,
    )


def summary_snapshot(
    summary: NotificationSummarySettings | None,
) -> NotificationSummarySettingsSnapshot | None:
    if summary is None:
        return None
    return NotificationSummarySettingsSnapshot(
        enabled=summary.enabled,
        bot_id=summary.bot_id,
        chat_id=summary.chat_id,
        timezone=summary.timezone,
        day_start_hour=summary.day_start_hour,
        night_start_hour=summary.night_start_hour,
    )


def mask_bot_token(bot_token: str | None) -> str | None:
    if not bot_token:
        return None
    prefix, separator, suffix = bot_token.partition(":")
    if separator:
        return f"{prefix}:***{suffix[-4:]}"
    if len(bot_token) <= 8:
        return "***"
    return f"{bot_token[:4]}***{bot_token[-4:]}"
