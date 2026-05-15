from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.lead_handling.use_cases import HandleLeadActionCallback, LeadActionCallback
from app.application.lead_handling.use_cases import HandleLeadBotPrivateMessage
from app.application.lead_handling.use_cases import PrivateBotCallback, PrivateBotMessage
from app.application.lead_handling.use_cases import _private_lead_card_keyboard
from app.domain.lead_handling import LeadBotSession, LeadClaimResult, LeadHandling, LeadHandlingActionResult
from app.domain.lead_handling import LeadHandlingActor, LeadHandlingEvent, LeadHandlingSummary


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


@pytest.mark.asyncio
async def test_start_message_sends_private_menu() -> None:
    sender = RecordingLeadBotSender()

    await HandleLeadBotPrivateMessage(
        handling_repository=InMemoryLeadHandlingRepository(),
        sender=sender,
        bot_token="token",
    ).execute_message(
        PrivateBotMessage(
            chat_id="100",
            actor=_actor("100", "manager"),
            text="/start",
        )
    )

    assert "Мои лиды" in sender.sent[-1].text
    assert sender.sent[-1].reply_markup == _main_menu_keyboard()


@pytest.mark.asyncio
async def test_my_leads_lists_only_owned_leads() -> None:
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=uuid4(),
        owner_telegram_user_id="100",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом в квартире",
        status="claimed",
    )
    repository.add_owned_summary(
        source_message_id=uuid4(),
        owner_telegram_user_id="200",
        source_chat_title="Other manager lead",
        text_preview="Чужой лид",
        status="claimed",
    )
    sender = RecordingLeadBotSender()

    await HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    ).execute_callback(
        PrivateBotCallback(
            action="my_leads",
            source_message_id=None,
            status=None,
            callback_query_id="cb1",
            chat_id="100",
            message_id=7,
            actor=_actor("100", "manager"),
        )
    )

    assert "Aqara" in sender.sent[-1].text
    assert "Other manager lead" not in sender.sent[-1].text


@pytest.mark.asyncio
async def test_my_leads_rows_open_private_lead_card() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="100",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом в квартире",
        telegram_message_url="https://t.me/aqararuchat/128974",
        status="claimed",
    )
    sender = RecordingLeadBotSender()
    handler = HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    )

    await handler.execute_callback(
        PrivateBotCallback(
            action="my_leads",
            source_message_id=None,
            status=None,
            callback_query_id="cb1",
            chat_id="100",
            message_id=7,
            actor=_actor("100", "manager"),
        )
    )
    await handler.execute_callback(
        PrivateBotCallback(
            action="open",
            source_message_id=source_message_id,
            status=None,
            callback_query_id="cb2",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert sender.sent[-2].reply_markup["inline_keyboard"][0][0]["callback_data"] == (
        f"lh:open:{source_message_id}"
    )
    assert "Нужен умный дом" in sender.sent[-1].text
    assert "https://t.me/aqararuchat/128974" in sender.sent[-1].text
    assert sender.sent[-1].reply_markup == _private_lead_card_keyboard(
        source_message_id,
        telegram_message_url="https://t.me/aqararuchat/128974",
    )


@pytest.mark.asyncio
async def test_private_open_rejects_lead_owned_by_another_operator() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="200",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом",
        status="claimed",
    )
    sender = RecordingLeadBotSender()
    handler = HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    )

    await handler.execute_callback(
        PrivateBotCallback(
            action="open",
            source_message_id=source_message_id,
            status=None,
            callback_query_id="cb2",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert "Этот лид закреплен за другим оператором" in sender.callback_answers[-1].text
    assert not sender.sent


@pytest.mark.asyncio
async def test_private_status_change_updates_handling_and_group_card() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="100",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом",
        status="claimed",
        sales_chat_id="-1001",
        sales_chat_message_id=99,
    )
    sender = RecordingLeadBotSender()

    await HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    ).execute_callback(
        PrivateBotCallback(
            action="status",
            source_message_id=source_message_id,
            status="waiting",
            callback_query_id="cb1",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert repository.handlings[source_message_id].status == "waiting"
    assert "Ждет" in sender.edits[-1].text


@pytest.mark.asyncio
async def test_comment_button_waits_for_next_message_and_saves_comment() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="100",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом",
        status="claimed",
    )
    handler = HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=RecordingLeadBotSender(),
        bot_token="token",
    )

    await handler.execute_callback(
        PrivateBotCallback(
            action="comment",
            source_message_id=source_message_id,
            status=None,
            callback_query_id="cb1",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )
    await handler.execute_message(
        PrivateBotMessage(
            chat_id="100",
            actor=_actor("100", "manager"),
            text="Написал, жду ответа",
        )
    )

    assert repository.handlings[source_message_id].last_comment == "Написал, жду ответа"
    assert ("main_bot", "100") not in repository.sessions


@pytest.mark.asyncio
async def test_private_status_change_records_failed_event_when_group_edit_fails() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="100",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом",
        status="claimed",
        sales_chat_id="-1001",
        sales_chat_message_id=99,
    )
    sender = RecordingLeadBotSender(fail_edit=True)

    await HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    ).execute_callback(
        PrivateBotCallback(
            action="status",
            source_message_id=source_message_id,
            status="waiting",
            callback_query_id="cb1",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert repository.handlings[source_message_id].status == "waiting"
    assert repository.events[-1].event_type == "callback_failed"
    assert repository.events[-1].payload["operation"] == "edit_group_card"


@pytest.mark.asyncio
async def test_private_status_change_rejects_lead_owned_by_another_operator() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="200",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом",
        status="claimed",
    )
    sender = RecordingLeadBotSender()

    await HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    ).execute_callback(
        PrivateBotCallback(
            action="status",
            source_message_id=source_message_id,
            status="waiting",
            callback_query_id="cb1",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert repository.handlings[source_message_id].status == "claimed"
    assert "закреплен за другим оператором" in (sender.callback_answers[-1].text or "")


@pytest.mark.asyncio
async def test_comment_text_rejects_lead_owned_by_another_operator() -> None:
    source_message_id = uuid4()
    repository = InMemoryLeadHandlingRepository()
    repository.add_session_state(
        bot_id="main_bot",
        telegram_user_id="100",
        state="awaiting_comment",
        payload={"source_message_id": str(source_message_id)},
    )
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="200",
        source_chat_title="Aqara.ru | Чат",
        text_preview="Нужен умный дом",
        status="claimed",
    )
    sender = RecordingLeadBotSender()

    await HandleLeadBotPrivateMessage(
        handling_repository=repository,
        sender=sender,
        bot_token="token",
    ).execute_message(
        PrivateBotMessage(
            chat_id="100",
            actor=_actor("100", "manager"),
            text="Комментарий чужому лиду",
        )
    )

    assert repository.handlings[source_message_id].last_comment is None
    assert "закреплен за другим оператором" in sender.sent[-1].text


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


@dataclass(frozen=True)
class RecordedSend:
    chat_id: str
    text: str
    reply_markup: dict[str, Any] | None


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
        self.handlings: dict[UUID, LeadHandling] = {}
        self.summaries: list[LeadHandlingSummary] = []
        self.sessions: dict[tuple[str, str], object] = {}
        self.events: list[LeadHandlingEvent] = []

    def add_owned_summary(
        self,
        *,
        source_message_id: UUID,
        owner_telegram_user_id: str,
        source_chat_title: str,
        text_preview: str,
        status: str,
        telegram_message_url: str | None = None,
        sales_chat_id: str | None = None,
        sales_chat_message_id: int | None = None,
    ) -> None:
        handling = _handling(
            source_message_id=source_message_id,
            status=status,
            owner_telegram_user_id=owner_telegram_user_id,
            owner_telegram_username="manager" if owner_telegram_user_id == "100" else "other",
            sales_chat_id=sales_chat_id,
            sales_chat_message_id=sales_chat_message_id,
        )
        handling = _with_source_fields(
            handling,
            source_chat_title=source_chat_title,
            text_preview=text_preview,
            telegram_message_url=telegram_message_url,
        )
        self.handlings[source_message_id] = handling
        self.handling = handling
        self.summaries.append(
            LeadHandlingSummary(
                id=handling.id,
                source_message_id=source_message_id,
                status=status,  # type: ignore[arg-type]
                owner_telegram_user_id=owner_telegram_user_id,
                owner_display_name=handling.owner_display_name,
                last_comment=handling.last_comment,
                sales_chat_id=handling.sales_chat_id,
                sales_chat_message_id=handling.sales_chat_message_id,
                updated_at=handling.updated_at,
                source_chat_title=source_chat_title,
                text_preview=text_preview,
                telegram_message_url=telegram_message_url,
            )
        )

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
        self.handlings[source_message_id] = self.handling
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
        self.handlings[source_message_id] = self.handling
        event = _event(self.handling, "marked_not_lead", actor, {})
        self.events.append(event)
        return LeadHandlingActionResult(handling=self.handling, event=event)

    async def change_status(
        self,
        *,
        source_message_id: UUID,
        status: str,
        actor: LeadHandlingActor,
    ) -> LeadHandlingActionResult:
        current = self.handlings[source_message_id]
        updated = _replace_handling(current, status=status)
        self.handlings[source_message_id] = updated
        self.handling = updated
        event = _event(updated, "status_changed", actor, {"status": status})
        self.events.append(event)
        return LeadHandlingActionResult(handling=updated, event=event)

    async def add_comment(
        self,
        *,
        source_message_id: UUID,
        comment: str,
        actor: LeadHandlingActor,
    ) -> LeadHandlingActionResult:
        current = self.handlings[source_message_id]
        updated = _replace_handling(current, last_comment=comment)
        self.handlings[source_message_id] = updated
        self.handling = updated
        event = _event(updated, "comment_added", actor, {"comment": comment})
        self.events.append(event)
        return LeadHandlingActionResult(handling=updated, event=event)

    async def list_for_owner(self, *, telegram_user_id: str, limit: int) -> list[LeadHandlingSummary]:
        return [
            summary
            for summary in self.summaries
            if summary.owner_telegram_user_id == telegram_user_id
        ][:limit]

    async def get_by_source_message_id(self, source_message_id: UUID) -> LeadHandling | None:
        return self.handlings.get(source_message_id, self.handling)

    def add_session_state(
        self,
        *,
        bot_id: str,
        telegram_user_id: str,
        state: str,
        payload: dict[str, object],
    ) -> None:
        self.sessions[(bot_id, telegram_user_id)] = LeadBotSession(
            bot_id=bot_id,
            telegram_user_id=telegram_user_id,
            state=state,
            payload=payload,
            updated_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
        )

    async def set_session_state(
        self,
        *,
        bot_id: str,
        telegram_user_id: str,
        state: str,
        payload: dict[str, object],
    ) -> LeadBotSession:
        self.add_session_state(
            bot_id=bot_id,
            telegram_user_id=telegram_user_id,
            state=state,
            payload=payload,
        )
        session = self.sessions[(bot_id, telegram_user_id)]
        assert isinstance(session, LeadBotSession)
        return session

    async def get_session_state(self, *, bot_id: str, telegram_user_id: str) -> LeadBotSession | None:
        session = self.sessions.get((bot_id, telegram_user_id))
        assert session is None or isinstance(session, LeadBotSession)
        return session

    async def clear_session_state(self, *, bot_id: str, telegram_user_id: str) -> None:
        self.sessions.pop((bot_id, telegram_user_id), None)

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
        self.sent: list[RecordedSend] = []
        self.edits: list[RecordedEdit] = []
        self.callback_answers: list[RecordedCallbackAnswer] = []

    async def send_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> Any:
        self.sent.append(RecordedSend(chat_id=chat_id, text=text, reply_markup=reply_markup))
        return object()

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


def _with_source_fields(
    handling: LeadHandling,
    *,
    source_chat_title: str,
    text_preview: str,
    telegram_message_url: str | None,
) -> LeadHandling:
    return LeadHandling(
        id=handling.id,
        source_message_id=handling.source_message_id,
        notification_outbox_id=handling.notification_outbox_id,
        sales_chat_id=handling.sales_chat_id,
        sales_chat_message_id=handling.sales_chat_message_id,
        status=handling.status,
        owner_telegram_user_id=handling.owner_telegram_user_id,
        owner_telegram_username=handling.owner_telegram_username,
        owner_display_name=handling.owner_display_name,
        last_comment=handling.last_comment,
        claimed_at=handling.claimed_at,
        closed_at=handling.closed_at,
        created_at=handling.created_at,
        updated_at=handling.updated_at,
        source_chat_title=source_chat_title,
        text_preview=text_preview,
        telegram_message_url=telegram_message_url,
    )


def _replace_handling(
    handling: LeadHandling,
    *,
    status: str | None = None,
    last_comment: str | None = None,
) -> LeadHandling:
    return LeadHandling(
        id=handling.id,
        source_message_id=handling.source_message_id,
        notification_outbox_id=handling.notification_outbox_id,
        sales_chat_id=handling.sales_chat_id,
        sales_chat_message_id=handling.sales_chat_message_id,
        status=(status or handling.status),  # type: ignore[arg-type]
        owner_telegram_user_id=handling.owner_telegram_user_id,
        owner_telegram_username=handling.owner_telegram_username,
        owner_display_name=handling.owner_display_name,
        last_comment=last_comment if last_comment is not None else handling.last_comment,
        claimed_at=handling.claimed_at,
        closed_at=handling.closed_at,
        created_at=handling.created_at,
        updated_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
        source_chat_title=handling.source_chat_title,
        text_preview=handling.text_preview,
        telegram_message_url=handling.telegram_message_url,
    )


def _main_menu_keyboard() -> dict[str, object]:
    return {"inline_keyboard": [[{"text": "Мои лиды", "callback_data": "lh:my_leads"}]]}


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
