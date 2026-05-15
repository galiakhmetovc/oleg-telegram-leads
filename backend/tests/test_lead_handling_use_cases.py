from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.lead_handling.use_cases import HandleLeadActionCallback, LeadActionCallback
from app.domain.lead_handling import LeadClaimResult, LeadHandling, LeadHandlingActionResult
from app.domain.lead_handling import LeadHandlingActor, LeadHandlingEvent


@pytest.mark.asyncio
async def test_claim_callback_claims_and_edits_group_message() -> None:
    source_message_id = uuid4()
    handling_repo = InMemoryLeadHandlingRepository()
    review_repo = InMemoryMessageReviewRepository()
    sender = RecordingLeadBotSender()

    result = await HandleLeadActionCallback(
        handling_repository=handling_repo,
        review_repository=review_repo,
        sender=sender,
        bot_token="token",
    ).execute(
        LeadActionCallback(
            action="claim",
            source_message_id=source_message_id,
            callback_query_id="cb1",
            chat_id="-1001",
            message_id=99,
            actor=_actor("100", "manager"),
            current_text="Лид ПУР\n\nСтатус: Новый",
        )
    )

    assert result.status == "claimed"
    assert handling_repo.handling is not None
    assert handling_repo.handling.owner_telegram_user_id == "100"
    assert sender.callback_answers[-1].text == "Заявка закреплена за вами"
    assert sender.edits[-1].text.endswith("Статус: Взял @manager")


@pytest.mark.asyncio
async def test_not_lead_callback_writes_review_and_edits_group_message() -> None:
    source_message_id = uuid4()
    handling_repo = InMemoryLeadHandlingRepository()
    review_repo = InMemoryMessageReviewRepository()
    sender = RecordingLeadBotSender()

    result = await HandleLeadActionCallback(
        handling_repository=handling_repo,
        review_repository=review_repo,
        sender=sender,
        bot_token="token",
    ).execute(
        LeadActionCallback(
            action="notlead",
            source_message_id=source_message_id,
            callback_query_id="cb1",
            chat_id="-1001",
            message_id=99,
            actor=_actor("100", "manager"),
            current_text="Лид ПУР\n\nСтатус: Новый",
        )
    )

    assert result.status == "not_lead"
    assert review_repo.saved[source_message_id].verdict == "not_lead"
    assert review_repo.cancelled == [
        (str(source_message_id), "lead marked not_lead from telegram bot")
    ]
    assert sender.callback_answers[-1].text == "Отмечено как не лид"
    assert sender.edits[-1].text.endswith("Статус: Не лид")


@pytest.mark.asyncio
async def test_existing_owner_conflict_answers_without_group_edit() -> None:
    source_message_id = uuid4()
    handling_repo = InMemoryLeadHandlingRepository()
    handling_repo.handling = _handling(
        source_message_id=source_message_id,
        status="claimed",
        owner_telegram_user_id="200",
        owner_telegram_username="owner",
    )
    sender = RecordingLeadBotSender()

    result = await HandleLeadActionCallback(
        handling_repository=handling_repo,
        review_repository=InMemoryMessageReviewRepository(),
        sender=sender,
        bot_token="token",
    ).execute(
        LeadActionCallback(
            action="claim",
            source_message_id=source_message_id,
            callback_query_id="cb1",
            chat_id="-1001",
            message_id=99,
            actor=_actor("100", "manager"),
            current_text="Лид ПУР\n\nСтатус: Новый",
        )
    )

    assert result.status == "claimed"
    assert sender.callback_answers[-1].text == "Уже взял @owner"
    assert sender.edits == []


@pytest.mark.asyncio
async def test_claim_callback_records_failed_event_when_group_edit_fails() -> None:
    source_message_id = uuid4()
    handling_repo = InMemoryLeadHandlingRepository()
    sender = RecordingLeadBotSender(fail_edit=True)

    result = await HandleLeadActionCallback(
        handling_repository=handling_repo,
        review_repository=InMemoryMessageReviewRepository(),
        sender=sender,
        bot_token="token",
    ).execute(
        LeadActionCallback(
            action="claim",
            source_message_id=source_message_id,
            callback_query_id="cb1",
            chat_id="-1001",
            message_id=99,
            actor=_actor("100", "manager"),
            current_text="Лид ПУР\n\nСтатус: Новый",
        )
    )

    assert result.status == "claimed"
    assert handling_repo.events[-1].event_type == "callback_failed"
    assert handling_repo.events[-1].payload["operation"] == "editMessageText"
    assert "editMessageText" in str(handling_repo.events[-1].payload["error"])
    assert sender.callback_answers[-1].callback_query_id == "cb1"


@dataclass(frozen=True)
class SavedReview:
    verdict: str | None
    comment: str
    tags: list[str]


@dataclass(frozen=True)
class RecordedEdit:
    chat_id: str
    message_id: int
    text: str
    reply_markup: dict[str, Any] | None


@dataclass(frozen=True)
class RecordedCallbackAnswer:
    callback_query_id: str
    text: str | None
    show_alert: bool


class InMemoryMessageReviewRepository:
    def __init__(self) -> None:
        self.saved: dict[UUID, SavedReview] = {}
        self.cancelled: list[tuple[str, str]] = []

    async def save_review(
        self,
        *,
        message_id: str,
        verdict: str | None,
        comment: str,
        tags: list[str],
    ) -> SavedReview:
        review = SavedReview(verdict=verdict, comment=comment, tags=tags)
        self.saved[UUID(message_id)] = review
        return review

    async def cancel_unsent_notifications_for_message(self, message_id: str, *, reason: str) -> int:
        self.cancelled.append((message_id, reason))
        return 1


class InMemoryLeadHandlingRepository:
    def __init__(self) -> None:
        self.handling: LeadHandling | None = None
        self.events: list[LeadHandlingEvent] = []

    async def claim(
        self,
        *,
        source_message_id: UUID,
        sales_chat_id: str,
        sales_chat_message_id: int,
        actor: LeadHandlingActor,
        notification_outbox_id: UUID | None = None,
    ) -> LeadClaimResult:
        if self.handling and self.handling.owner_telegram_user_id not in {None, actor.telegram_user_id}:
            event = _event(self.handling, "callback_failed", actor, {"reason": "already_claimed"})
            self.events.append(event)
            return LeadClaimResult(handling=self.handling, event=event, already_claimed=True)
        self.handling = _handling(
            source_message_id=source_message_id,
            status="claimed",
            owner_telegram_user_id=actor.telegram_user_id,
            owner_telegram_username=actor.telegram_username,
            sales_chat_id=sales_chat_id,
            sales_chat_message_id=sales_chat_message_id,
        )
        event = _event(
            self.handling,
            "claimed",
            actor,
            {"sales_chat_id": sales_chat_id, "sales_chat_message_id": sales_chat_message_id},
        )
        self.events.append(event)
        return LeadClaimResult(handling=self.handling, event=event, already_claimed=False)

    async def mark_not_lead(
        self,
        *,
        source_message_id: UUID,
        sales_chat_id: str | None,
        sales_chat_message_id: int | None,
        actor: LeadHandlingActor,
        notification_outbox_id: UUID | None = None,
    ) -> LeadHandlingActionResult:
        self.handling = _handling(
            source_message_id=source_message_id,
            status="not_lead",
            sales_chat_id=sales_chat_id,
            sales_chat_message_id=sales_chat_message_id,
        )
        event = _event(self.handling, "marked_not_lead", actor, {})
        self.events.append(event)
        return LeadHandlingActionResult(handling=self.handling, event=event)

    async def record_event(
        self,
        *,
        source_message_id: UUID,
        event_type: str,
        actor: LeadHandlingActor,
        payload: dict[str, object],
    ) -> LeadHandlingEvent:
        handling = self.handling or _handling(source_message_id=source_message_id, status="new")
        event = _event(handling, event_type, actor, payload)
        self.events.append(event)
        return event


class RecordingLeadBotSender:
    def __init__(self, *, fail_edit: bool = False) -> None:
        self.fail_edit = fail_edit
        self.edits: list[RecordedEdit] = []
        self.callback_answers: list[RecordedCallbackAnswer] = []

    async def edit_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> Any:
        if self.fail_edit:
            raise RuntimeError("editMessageText failed")
        self.edits.append(
            RecordedEdit(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
        )
        return object()

    async def answer_callback_query(
        self,
        *,
        bot_token: str,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        self.callback_answers.append(
            RecordedCallbackAnswer(
                callback_query_id=callback_query_id,
                text=text,
                show_alert=show_alert,
            )
        )


def _actor(telegram_user_id: str, username: str) -> LeadHandlingActor:
    return LeadHandlingActor(
        telegram_user_id=telegram_user_id,
        telegram_username=username,
        display_name=username.title(),
    )


def _handling(
    *,
    source_message_id: UUID,
    status: str,
    owner_telegram_user_id: str | None = None,
    owner_telegram_username: str | None = None,
    sales_chat_id: str | None = None,
    sales_chat_message_id: int | None = None,
) -> LeadHandling:
    now = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
    return LeadHandling(
        id=uuid4(),
        source_message_id=source_message_id,
        notification_outbox_id=None,
        sales_chat_id=sales_chat_id,
        sales_chat_message_id=sales_chat_message_id,
        status=status,  # type: ignore[arg-type]
        owner_telegram_user_id=owner_telegram_user_id,
        owner_telegram_username=owner_telegram_username,
        owner_display_name=owner_telegram_username,
        last_comment=None,
        claimed_at=now if status == "claimed" else None,
        closed_at=now if status == "not_lead" else None,
        created_at=now,
        updated_at=now,
    )


def _event(
    handling: LeadHandling,
    event_type: str,
    actor: LeadHandlingActor,
    payload: dict[str, object],
) -> LeadHandlingEvent:
    return LeadHandlingEvent(
        id=uuid4(),
        lead_handling_id=handling.id,
        source_message_id=handling.source_message_id,
        actor_telegram_user_id=actor.telegram_user_id,
        actor_telegram_username=actor.telegram_username,
        actor_display_name=actor.display_name,
        event_type=event_type,  # type: ignore[arg-type]
        payload=payload,
        created_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )
