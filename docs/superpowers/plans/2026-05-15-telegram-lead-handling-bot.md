# Telegram Lead Handling Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Telegram-only mini-CRM where sales operators claim lead cards in a group, mark false leads, and manage their own claimed leads through private bot chat.

**Architecture:** Keep lead detection and notification routing intact. Add an interactive notification mode that sends one Telegram message per lead with inline buttons, then add a bot update worker that handles callback queries and private messages. Store current lead handling state in `lead_handlings` and append all operator actions to `lead_handling_events`.

**Tech Stack:** FastAPI, SQLAlchemy Core/Alembic, PostgreSQL JSONB, async repositories, httpx Telegram Bot API adapter, Docker Compose workers, pytest/pytest-asyncio.

---

## File Structure

Create:

- `backend/alembic/versions/0035_lead_handling_bot.py` - lead handling, events, and private bot session state tables.
- `backend/app/domain/lead_handling.py` - immutable domain records and status/event literals.
- `backend/app/application/lead_handling/__init__.py` - package marker.
- `backend/app/application/lead_handling/ports.py` - repository and Telegram bot sender ports.
- `backend/app/application/lead_handling/use_cases.py` - claim/not-lead/status/comment/menu use cases.
- `backend/app/infrastructure/persistence/lead_handling_repository.py` - PostgreSQL implementation.
- `backend/app/infrastructure/telegram/bot_updates.py` - Telegram Bot API `getUpdates` adapter and update DTO parsing.
- `backend/app/cli/telegram_bot_worker.py` - polling worker for callbacks and private chat messages.
- `backend/tests/test_lead_handling_repository.py` - persistence behavior.
- `backend/tests/test_lead_handling_use_cases.py` - claim/not-lead/private menu behavior.
- `backend/tests/test_telegram_bot_worker.py` - update polling and dispatch behavior.

Modify:

- `backend/app/infrastructure/persistence/tables.py` - table metadata for new tables.
- `backend/app/domain/notifications.py` - route delivery mode and sender result/keyboard DTOs.
- `backend/app/infrastructure/persistence/notification_settings_repository.py` - persist/read route `delivery_mode`.
- `backend/app/api/notifications.py` - expose `delivery_mode` in settings API.
- `backend/app/application/notifications/use_cases.py` - flush interactive cards one-by-one and wire inline buttons.
- `backend/app/application/notifications/ports.py` - sender method signatures for keyboard/edit/callback answer.
- `backend/app/infrastructure/notifications/telegram_sender.py` - Bot API `reply_markup`, `editMessageText`, `answerCallbackQuery`.
- `backend/app/infrastructure/persistence/notification_outbox_repository.py` - no schema change expected, but repository tests may need interactive helper behavior.
- `backend/app/cli/notification_dispatcher.py` - pass `LeadHandlingRepository` into flush use case.
- `docker-compose.yml` - add `lead-bot` worker service.
- `backend/tests/test_notification_outbox.py` - interactive route behavior.
- `backend/tests/test_notification_settings_api.py` - delivery mode serialization.
- `backend/tests/test_worker_notifications.py` - ensure current enqueue path still works.
- `state/current.md` - update handoff after implementation and verification.

Do not modify frontend in the first pass. Operators work in Telegram; web remains admin/analytics.

---

### Task 1: Add Lead Handling Storage

**Files:**
- Create: `backend/alembic/versions/0035_lead_handling_bot.py`
- Create: `backend/app/domain/lead_handling.py`
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Test: `backend/tests/test_lead_handling_repository.py`

- [ ] **Step 1: Write failing repository tests**

Add tests for upsert-by-source-message, immutable event append, owner race behavior, and private session state.

```python
@pytest.mark.asyncio
async def test_claim_creates_handling_and_event(session_factory):
    repository = PostgresLeadHandlingRepository(session_factory)
    source_message_id = uuid4()

    result = await repository.claim(
        source_message_id=source_message_id,
        sales_chat_id="-1001",
        sales_chat_message_id=42,
        actor=LeadHandlingActor(
            telegram_user_id="100",
            telegram_username="manager",
            display_name="Manager",
        ),
    )

    assert result.handling.status == "claimed"
    assert result.handling.owner_telegram_user_id == "100"
    assert result.event.event_type == "claimed"
```

Also include:

```python
@pytest.mark.asyncio
async def test_second_claim_from_other_user_does_not_replace_owner(session_factory):
    repository = PostgresLeadHandlingRepository(session_factory)
    source_message_id = uuid4()
    await repository.claim(source_message_id=source_message_id, sales_chat_id="-1001", sales_chat_message_id=1, actor=_actor("100", "first"))

    result = await repository.claim(source_message_id=source_message_id, sales_chat_id="-1001", sales_chat_message_id=1, actor=_actor("200", "second"))

    assert result.handling.owner_telegram_user_id == "100"
    assert result.already_claimed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_lead_handling_repository.py -q`

Expected: FAIL because `app.domain.lead_handling` or `PostgresLeadHandlingRepository` does not exist.

- [ ] **Step 3: Add migration and table metadata**

Create tables:

```python
op.create_table(
    "lead_handlings",
    sa.Column("id", sa.UUID(), primary_key=True),
    sa.Column("source_message_id", sa.UUID(), nullable=False),
    sa.Column("notification_outbox_id", sa.UUID(), nullable=True),
    sa.Column("sales_chat_id", sa.Text(), nullable=True),
    sa.Column("sales_chat_message_id", sa.BigInteger(), nullable=True),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("owner_telegram_user_id", sa.Text(), nullable=True),
    sa.Column("owner_telegram_username", sa.Text(), nullable=True),
    sa.Column("owner_display_name", sa.Text(), nullable=True),
    sa.Column("last_comment", sa.Text(), nullable=True),
    sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["source_message_id"], ["telegram_source_messages.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["notification_outbox_id"], ["notification_outbox.id"], ondelete="SET NULL"),
    sa.UniqueConstraint("source_message_id", name="uq_lead_handlings_source_message"),
    sa.CheckConstraint(
        "status IN ('new', 'claimed', 'contacted', 'waiting', 'closed', 'not_lead')",
        name="ck_lead_handlings_status",
    ),
)
```

Add `lead_handling_events` and `lead_bot_sessions`:

```python
op.create_table(
    "lead_handling_events",
    sa.Column("id", sa.UUID(), primary_key=True),
    sa.Column("lead_handling_id", sa.UUID(), nullable=False),
    sa.Column("source_message_id", sa.UUID(), nullable=False),
    sa.Column("actor_telegram_user_id", sa.Text(), nullable=True),
    sa.Column("actor_telegram_username", sa.Text(), nullable=True),
    sa.Column("actor_display_name", sa.Text(), nullable=True),
    sa.Column("event_type", sa.Text(), nullable=False),
    sa.Column("payload", postgresql.JSONB(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["lead_handling_id"], ["lead_handlings.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["source_message_id"], ["telegram_source_messages.id"], ondelete="CASCADE"),
)
```

`lead_bot_sessions` stores private-chat state:

```python
op.create_table(
    "lead_bot_sessions",
    sa.Column("bot_id", sa.Text(), nullable=False),
    sa.Column("telegram_user_id", sa.Text(), nullable=False),
    sa.Column("state", sa.Text(), nullable=False),
    sa.Column("payload", postgresql.JSONB(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("bot_id", "telegram_user_id"),
)
```

Mirror all tables in `backend/app/infrastructure/persistence/tables.py`.

- [ ] **Step 4: Add domain records and repository implementation**

Domain file must include:

```python
LeadHandlingStatus = Literal["new", "claimed", "contacted", "waiting", "closed", "not_lead"]
LeadHandlingEventType = Literal[
    "created",
    "claimed",
    "marked_not_lead",
    "status_changed",
    "comment_added",
    "group_message_edited",
    "callback_failed",
]
```

Implement repository methods:

- `claim(...) -> LeadClaimResult`
- `mark_not_lead(...) -> LeadHandlingActionResult`
- `change_status(...) -> LeadHandlingActionResult`
- `add_comment(...) -> LeadHandlingActionResult`
- `list_for_owner(...) -> list[LeadHandlingSummary]`
- `get_by_source_message_id(...)`
- `set_session_state(...)`
- `get_session_state(...)`
- `clear_session_state(...)`

Use `INSERT .. ON CONFLICT (source_message_id) DO UPDATE` for idempotent creation, but do not replace an existing owner when another Telegram user claims the same lead.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_lead_handling_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0035_lead_handling_bot.py \
  backend/app/domain/lead_handling.py \
  backend/app/infrastructure/persistence/tables.py \
  backend/app/infrastructure/persistence/lead_handling_repository.py \
  backend/tests/test_lead_handling_repository.py
git commit -m "feat: add lead handling persistence"
```

---

### Task 2: Add Interactive Notification Route Mode

**Files:**
- Modify: `backend/app/domain/notifications.py`
- Modify: `backend/app/infrastructure/persistence/notification_settings_repository.py`
- Modify: `backend/app/api/notifications.py`
- Test: `backend/tests/test_notification_settings_api.py`

- [ ] **Step 1: Write failing API test for route `delivery_mode`**

Extend `test_get_settings_contains_masked_notification_bots_chats_and_routes` with:

```python
"delivery_mode": "interactive",
```

and assert:

```python
assert notifications["routes"][0]["delivery_mode"] == "interactive"
```

Add a second assertion that missing `delivery_mode` defaults to `"batched"` when reading old settings.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_notification_settings_api.py::test_get_settings_contains_masked_notification_bots_chats_and_routes -q`

Expected: FAIL because `delivery_mode` is ignored or rejected.

- [ ] **Step 3: Implement route delivery mode**

In `backend/app/domain/notifications.py`:

```python
NotificationDeliveryMode = Literal["batched", "interactive"]

@dataclass(frozen=True)
class NotificationRoute:
    ...
    delivery_mode: NotificationDeliveryMode = "batched"
```

In API schemas:

```python
delivery_mode: Literal["batched", "interactive"] = "batched"
```

In repository read/write:

```python
delivery_mode="interactive" if data.get("delivery_mode") == "interactive" else "batched"
```

and include `"delivery_mode": route.delivery_mode` in `_route_to_dict`.

Validation rule in `UpdateNotificationSettings`: route mode must be `batched` or `interactive`.

- [ ] **Step 4: Run settings tests**

Run: `cd backend && uv run pytest tests/test_notification_settings_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/notifications.py \
  backend/app/infrastructure/persistence/notification_settings_repository.py \
  backend/app/api/notifications.py \
  backend/tests/test_notification_settings_api.py
git commit -m "feat: add interactive notification route mode"
```

---

### Task 3: Extend Telegram Sender For Interactive Cards

**Files:**
- Modify: `backend/app/domain/notifications.py`
- Modify: `backend/app/application/notifications/ports.py`
- Modify: `backend/app/infrastructure/notifications/telegram_sender.py`
- Test: `backend/tests/test_notification_outbox.py`

- [ ] **Step 1: Write failing sender-port tests**

In `RecordingTelegramMessageSender`, capture optional `reply_markup`:

```python
class RecordingTelegramMessageSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, dict[str, Any] | None]] = []

    async def send_text(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> TelegramSendResult:
        self.sent.append((bot_token, chat_id, text, reply_markup))
        return TelegramSendResult(message_id=len(self.sent), chat_id=chat_id)
```

The test should fail until the port/domain method accepts `reply_markup`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_notification_outbox.py::test_flush_interactive_notification_sends_inline_buttons -q`

Expected: FAIL because test/function does not exist or sender signature is old.

- [ ] **Step 3: Implement Bot API methods**

Update `TelegramMessageSender` protocol:

```python
async def send_text(
    self,
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> TelegramSendResult: ...

async def edit_text(
    self,
    *,
    bot_token: str,
    chat_id: str,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> TelegramSendResult: ...

async def answer_callback_query(
    self,
    *,
    bot_token: str,
    callback_query_id: str,
    text: str | None = None,
    show_alert: bool = False,
) -> None: ...
```

Update `HttpTelegramMessageSender`:

- `send_text` posts to `sendMessage` and includes `reply_markup` only when not `None`.
- `edit_text` posts to `editMessageText`.
- `answer_callback_query` posts to `answerCallbackQuery`.

- [ ] **Step 4: Run notification tests**

Run: `cd backend && uv run pytest tests/test_notification_outbox.py tests/test_notification_settings_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/notifications.py \
  backend/app/application/notifications/ports.py \
  backend/app/infrastructure/notifications/telegram_sender.py \
  backend/tests/test_notification_outbox.py
git commit -m "feat: support telegram inline notification actions"
```

---

### Task 4: Send Interactive Lead Cards Without Batching

**Files:**
- Modify: `backend/app/application/notifications/use_cases.py`
- Modify: `backend/app/cli/notification_dispatcher.py`
- Test: `backend/tests/test_notification_outbox.py`

- [ ] **Step 1: Write failing interactive flush tests**

Add:

```python
@pytest.mark.asyncio
async def test_flush_interactive_notification_sends_inline_buttons() -> None:
    now = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
    source_message_id = uuid4()
    settings = _notification_settings(delivery_mode="interactive")
    outbox = InMemoryNotificationOutboxRepository(now)
    sender = RecordingTelegramMessageSender()
    outbox.items = [
        NotificationOutboxItem(
            id=uuid4(),
            route_id="hot",
            bot_id="main_bot",
            chat_id="sales_chat",
            source_message_id=source_message_id,
            enrichment_job_id=uuid4(),
            text="Лид ПУР\n\nТекст: нужен умный дом",
            status="pending",
            attempts=0,
            last_error=None,
            created_at=now,
            sent_at=None,
        )
    ]

    sent = await FlushNotificationOutbox(
        settings_repository=InMemoryNotificationSettingsRepository(settings),
        outbox_repository=outbox,
        sender=sender,
        flush_interval=timedelta(minutes=5),
    ).execute(now=now)

    assert len(sent) == 1
    assert sender.sent[0][3] == {
        "inline_keyboard": [[
            {"text": "Взял", "callback_data": f"lh:claim:{source_message_id}"},
            {"text": "Не лид", "callback_data": f"lh:notlead:{source_message_id}"},
        ]]
    }
```

Add another test:

```python
@pytest.mark.asyncio
async def test_interactive_route_requires_source_message_id() -> None:
    ...
    assert outbox.failed_ids == [item.id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_notification_outbox.py::test_flush_interactive_notification_sends_inline_buttons tests/test_notification_outbox.py::test_interactive_route_requires_source_message_id -q`

Expected: FAIL because interactive mode is not handled.

- [ ] **Step 3: Implement interactive path in flush use case**

In `FlushNotificationOutbox.execute`, separate pending items by route:

- lookup route by `route_id`;
- if `delivery_mode == "interactive"`, send one item immediately;
- require `item.source_message_id`;
- call `sender.send_text(..., reply_markup=_lead_action_keyboard(item.source_message_id))`;
- mark each item sent individually;
- keep existing packing behavior for batched routes.

Helper:

```python
def _lead_action_keyboard(source_message_id: UUID) -> dict[str, Any]:
    return {
        "inline_keyboard": [[
            {"text": "Взял", "callback_data": f"lh:claim:{source_message_id}"},
            {"text": "Не лид", "callback_data": f"lh:notlead:{source_message_id}"},
        ]]
    }
```

Do not add lead handling state yet; callback processing creates it.

- [ ] **Step 4: Run notification tests**

Run: `cd backend && uv run pytest tests/test_notification_outbox.py tests/test_worker_notifications.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/notifications/use_cases.py \
  backend/app/cli/notification_dispatcher.py \
  backend/tests/test_notification_outbox.py \
  backend/tests/test_worker_notifications.py
git commit -m "feat: send interactive lead notifications"
```

---

### Task 5: Handle Group Buttons `Взял` And `Не лид`

**Files:**
- Create: `backend/app/application/lead_handling/ports.py`
- Create: `backend/app/application/lead_handling/use_cases.py`
- Modify: `backend/app/infrastructure/persistence/analytics_repository.py` if reuse is not clean
- Test: `backend/tests/test_lead_handling_use_cases.py`

- [ ] **Step 1: Write failing use-case tests**

Use in-memory repositories and fake sender:

```python
@pytest.mark.asyncio
async def test_claim_callback_claims_and_edits_group_message() -> None:
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
    assert sender.edits[-1].text.endswith("Статус: Взял @manager")
```

Add:

```python
@pytest.mark.asyncio
async def test_not_lead_callback_writes_review_and_edits_group_message() -> None:
    ...
    assert review_repo.saved[source_message_id].verdict == "not_lead"
    assert review_repo.cancelled == [
        (str(source_message_id), "lead marked not_lead from telegram bot")
    ]
```

Add Telegram API failure coverage:

```python
@pytest.mark.asyncio
async def test_claim_callback_records_failed_event_when_group_edit_fails() -> None:
    handling_repo = InMemoryLeadHandlingRepository()
    sender = FailingLeadBotSender(fail_edit=True)

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
    assert "editMessageText" in handling_repo.events[-1].payload["error"]
    assert sender.callback_answers[-1].callback_query_id == "cb1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_lead_handling_use_cases.py -q`

Expected: FAIL because use cases do not exist.

- [ ] **Step 3: Implement callback use case**

Create DTOs:

```python
@dataclass(frozen=True)
class LeadActionCallback:
    action: Literal["claim", "notlead"]
    source_message_id: UUID
    callback_query_id: str
    chat_id: str
    message_id: int
    actor: LeadHandlingActor
    current_text: str
```

Behavior:

- `claim`: call `LeadHandlingRepository.claim`, answer callback, edit group card with current owner.
- `notlead`: call `LeadHandlingRepository.mark_not_lead`, save
  `message_reviews` verdict `not_lead`, call
  `cancel_unsent_notifications_for_message` with reason
  `lead marked not_lead from telegram bot`, answer callback, edit group card.
- Existing owner conflict: answer callback with `Уже взял @owner`, no edit.
- Telegram API failures from `answer_callback_query` and `edit_text` must not
  roll back the saved handling state. Catch sender exceptions, append a
  `callback_failed` event with `operation`, `chat_id`, `message_id`,
  `callback_query_id`, and `error`, then log the exception.
- If `answer_callback_query` fails before or after the state change, still try to
  edit the group message when it is safe to do so; if both fail, record one
  `callback_failed` event per failed operation.

Define a small `MessageReviewWriter` port instead of depending directly on `PostgresAnalyticsRepository`:

```python
class MessageReviewWriter(Protocol):
    async def save_review(self, message_id: str, verdict: str | None, comment: str, tags: list[str]) -> Any: ...
    async def cancel_unsent_notifications_for_message(self, message_id: str, *, reason: str) -> int: ...
```

- [ ] **Step 4: Run use-case tests**

Run: `cd backend && uv run pytest tests/test_lead_handling_use_cases.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/lead_handling \
  backend/tests/test_lead_handling_use_cases.py
git commit -m "feat: handle lead action callbacks"
```

---

### Task 6: Add Telegram Bot Update Polling Worker

**Files:**
- Create: `backend/app/infrastructure/telegram/bot_updates.py`
- Create: `backend/app/cli/telegram_bot_worker.py`
- Modify: `docker-compose.yml`
- Test: `backend/tests/test_telegram_bot_worker.py`

- [ ] **Step 1: Write failing worker tests**

Test callback parsing:

```python
def test_parse_claim_callback_update():
    update = TelegramBotUpdate.from_payload({
        "update_id": 10,
        "callback_query": {
            "id": "cb1",
            "from": {"id": 100, "username": "manager", "first_name": "Ivan"},
            "message": {"message_id": 99, "chat": {"id": -1001}, "text": "Лид ПУР"},
            "data": f"lh:claim:{source_message_id}",
        },
    })

    assert update.callback.action == "claim"
    assert update.callback.source_message_id == source_message_id
```

Test polling dispatch:

```python
@pytest.mark.asyncio
async def test_worker_dispatches_callback_and_advances_offset():
    client = FakeBotUpdateClient([...])
    offsets = InMemoryBotOffsetRepository()
    worker = TelegramBotWorker(...)

    await worker.run_once()

    assert handler.callbacks == ["claim"]
    assert offsets.offsets["main_bot"] == 11
```

Test private callback and message dispatch:

```python
@pytest.mark.asyncio
async def test_worker_dispatches_private_callbacks_to_private_handler():
    client = FakeBotUpdateClient([
        _callback_update(
            update_id=20,
            chat_id=100,
            data="lh:my_leads",
            chat_type="private",
        ),
        _callback_update(
            update_id=21,
            chat_id=100,
            data=f"lh:open:{source_message_id}",
            chat_type="private",
        ),
        _callback_update(
            update_id=22,
            chat_id=100,
            data=f"lh:status:{source_message_id}:waiting",
            chat_type="private",
        ),
        _callback_update(
            update_id=23,
            chat_id=100,
            data=f"lh:comment:{source_message_id}",
            chat_type="private",
        ),
    ])
    private_handler = RecordingPrivateHandler()
    worker = TelegramBotWorker(..., private_handler=private_handler)

    await worker.run_once()

    assert [callback.action for callback in private_handler.callbacks] == [
        "my_leads",
        "open",
        "status",
        "comment",
    ]
```

```python
@pytest.mark.asyncio
async def test_worker_dispatches_private_text_to_private_handler():
    client = FakeBotUpdateClient([
        _private_message_update(update_id=30, chat_id=100, text="Написал, жду ответа")
    ])
    private_handler = RecordingPrivateHandler()
    worker = TelegramBotWorker(..., private_handler=private_handler)

    await worker.run_once()

    assert private_handler.messages[-1].text == "Написал, жду ответа"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_telegram_bot_worker.py -q`

Expected: FAIL because worker/update parser does not exist.

- [ ] **Step 3: Implement update client and worker**

`HttpTelegramBotUpdateClient` methods:

- `get_updates(bot_token, offset, timeout_seconds) -> list[TelegramBotUpdate]`

Use Bot API `getUpdates` with `allowed_updates=["callback_query", "message"]`.

`telegram_bot_worker.py`:

- loads notification settings;
- finds enabled bots used by interactive routes;
- polls each bot;
- dispatches group callback queries with `lh:claim:*` and `lh:notlead:*` to
  `HandleLeadActionCallback`;
- dispatches private callback queries with `lh:my_leads`, `lh:open:*`,
  `lh:status:*:*`, and `lh:comment:*` to `HandleLeadBotPrivateMessage`;
- dispatches private text messages, including `/start` and awaiting-comment
  text, to `HandleLeadBotPrivateMessage`;
- ignores non-private ordinary messages so the bot does not treat sales group
  discussion as comments;
- stores update offsets in repository/session state.

Add persistence for offsets either in `lead_bot_sessions` with reserved `telegram_user_id = "__offset__"` or a dedicated table if Task 1 created one. Prefer dedicated table if added in migration; otherwise keep a focused `lead_bot_sessions` offset row and document it in code.

Add Docker service:

```yaml
  lead-bot:
    build:
      context: ./backend
    logging: *default-logging
    command: python -m app.cli.telegram_bot_worker --interval 2 --timeout 25
    environment:
      PUR_DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-pur_leads}:${POSTGRES_PASSWORD:-pur_leads_dev_password}@postgres:5432/${POSTGRES_DB:-pur_leads_v2}
      PUR_ENVIRONMENT: development
    volumes:
      - ./backend:/app
    depends_on:
      migrate:
        condition: service_completed_successfully
```

- [ ] **Step 4: Run worker tests**

Run: `cd backend && uv run pytest tests/test_telegram_bot_worker.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/telegram/bot_updates.py \
  backend/app/cli/telegram_bot_worker.py \
  backend/tests/test_telegram_bot_worker.py \
  docker-compose.yml
git commit -m "feat: add telegram lead bot worker"
```

---

### Task 7: Add Private Bot Menu And `Мои лиды`

**Files:**
- Modify: `backend/app/application/lead_handling/use_cases.py`
- Modify: `backend/app/infrastructure/telegram/bot_updates.py`
- Modify: `backend/app/cli/telegram_bot_worker.py`
- Test: `backend/tests/test_lead_handling_use_cases.py`
- Test: `backend/tests/test_telegram_bot_worker.py`

This MVP implements `/start` and `Мои лиды`. The spec's `Новые`, `В работе`,
and `Закрытые` private filters are deferred until the base private workflow is
working; they are filtered variants of `Мои лиды`, not separate infrastructure.

- [ ] **Step 1: Write failing private-menu tests**

```python
@pytest.mark.asyncio
async def test_start_message_sends_private_menu() -> None:
    sender = RecordingLeadBotSender()

    await HandleLeadBotPrivateMessage(...).execute(
        PrivateBotMessage(
            chat_id="100",
            actor=_actor("100", "manager"),
            text="/start",
        )
    )

    assert "Мои лиды" in sender.sent[-1].text
```

```python
@pytest.mark.asyncio
async def test_my_leads_lists_only_owned_leads() -> None:
    ...
    assert "Aqara" in sender.sent[-1].text
    assert "Other manager lead" not in sender.sent[-1].text
```

Add a card-opening test so the list has a usable next step:

```python
@pytest.mark.asyncio
async def test_my_leads_rows_open_private_lead_card() -> None:
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
            callback_query_id="cb2",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert sender.sent[-2].reply_markup["inline_keyboard"][0][0]["callback_data"] == f"lh:open:{source_message_id}"
    assert "Нужен умный дом" in sender.sent[-1].text
    assert "https://t.me/aqararuchat/128974" in sender.sent[-1].text
    assert sender.sent[-1].reply_markup == _private_lead_card_keyboard(source_message_id)
```

Add ownership protection:

```python
@pytest.mark.asyncio
async def test_private_open_rejects_lead_owned_by_another_operator() -> None:
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
            callback_query_id="cb2",
            chat_id="100",
            message_id=8,
            actor=_actor("100", "manager"),
        )
    )

    assert "Этот лид закреплен за другим оператором" in sender.callback_answers[-1].text
    assert not sender.sent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_lead_handling_use_cases.py::test_start_message_sends_private_menu tests/test_lead_handling_use_cases.py::test_my_leads_lists_only_owned_leads tests/test_lead_handling_use_cases.py::test_my_leads_rows_open_private_lead_card tests/test_lead_handling_use_cases.py::test_private_open_rejects_lead_owned_by_another_operator -q`

Expected: FAIL because private message handler does not exist.

- [ ] **Step 3: Implement private message handler**

Handle:

- `/start`: send menu with inline keyboard `Мои лиды`.
- `Мои лиды` button/callback: list leads where owner is actor. Each row must be
  an inline button using `lh:open:<source_message_id>`.
- `lh:open:<source_message_id>` callback: render a private lead card with text
  preview, source, source-message link when available, status, last comment, and
  action buttons for status/comment/source opening.
- Before rendering a private card, load the handling row and require
  `owner_telegram_user_id == actor.telegram_user_id`. If not, answer
  `Этот лид закреплен за другим оператором` and do not expose lead text or
  action buttons.
- Plain text when no session state: send help/menu.

Repository `list_for_owner` should join enough source-message/source-chat data for useful rows:

- source chat title;
- source message text preview;
- source-message Telegram URL, when it can be derived from source chat and
  Telegram message id;
- status;
- updated_at.

Private lead card keyboard:

```python
def _private_lead_card_keyboard(source_message_id: UUID) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Написал", "callback_data": f"lh:status:{source_message_id}:contacted"},
                {"text": "Ждет", "callback_data": f"lh:status:{source_message_id}:waiting"},
            ],
            [
                {"text": "Закрыт", "callback_data": f"lh:status:{source_message_id}:closed"},
                {"text": "Комментарий", "callback_data": f"lh:comment:{source_message_id}"},
            ],
            [
                {"text": "Открыть источник", "url": "<telegram_message_url>"},
            ],
        ]
    }
```

Omit the `Открыть источник` row when `telegram_message_url` is unavailable;
do not create a callback button that cannot open anything.

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_lead_handling_use_cases.py tests/test_telegram_bot_worker.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/lead_handling/use_cases.py \
  backend/app/infrastructure/telegram/bot_updates.py \
  backend/app/cli/telegram_bot_worker.py \
  backend/tests/test_lead_handling_use_cases.py \
  backend/tests/test_telegram_bot_worker.py
git commit -m "feat: show claimed leads in telegram bot"
```

---

### Task 8: Add Private Status And Comment Actions

**Files:**
- Modify: `backend/app/application/lead_handling/use_cases.py`
- Modify: `backend/app/infrastructure/persistence/lead_handling_repository.py`
- Test: `backend/tests/test_lead_handling_use_cases.py`

- [ ] **Step 1: Write failing tests for status/comment**

```python
@pytest.mark.asyncio
async def test_private_status_change_updates_handling_and_group_card() -> None:
    ...
    await handler.execute_callback("lh:status:<source_message_id>:waiting")
    assert repository.handling.status == "waiting"
    assert "Ждет" in sender.group_edits[-1].text
```

```python
@pytest.mark.asyncio
async def test_comment_button_waits_for_next_message_and_saves_comment() -> None:
    ...
    await handler.execute_callback("lh:comment:<source_message_id>")
    await handler.execute_message(text="Написал, жду ответа")
    assert repository.handling.last_comment == "Написал, жду ответа"
```

Add private send/edit failure coverage:

```python
@pytest.mark.asyncio
async def test_private_status_change_records_failed_event_when_group_edit_fails() -> None:
    sender = FailingLeadBotSender(fail_group_edit=True)

    await handler.execute_callback(f"lh:status:{source_message_id}:waiting")

    assert repository.handling.status == "waiting"
    assert repository.events[-1].event_type == "callback_failed"
    assert repository.events[-1].payload["operation"] == "edit_group_card"
```

Add ownership protection for mutation and follow-up comment text:

```python
@pytest.mark.asyncio
async def test_private_status_change_rejects_lead_owned_by_another_operator() -> None:
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="200",
        status="claimed",
    )

    await handler.execute_callback(
        f"lh:status:{source_message_id}:waiting",
        actor=_actor("100", "manager"),
    )

    assert repository.handling.status == "claimed"
    assert "закреплен за другим оператором" in sender.callback_answers[-1].text
```

```python
@pytest.mark.asyncio
async def test_comment_text_rejects_lead_owned_by_another_operator() -> None:
    repository.add_session_state(
        bot_id="main_bot",
        telegram_user_id="100",
        state="awaiting_comment",
        payload={"source_message_id": str(source_message_id)},
    )
    repository.add_owned_summary(
        source_message_id=source_message_id,
        owner_telegram_user_id="200",
        status="claimed",
    )

    await handler.execute_message(
        text="Комментарий чужому лиду",
        actor=_actor("100", "manager"),
    )

    assert repository.handling.last_comment is None
    assert "закреплен за другим оператором" in sender.sent[-1].text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_lead_handling_use_cases.py::test_private_status_change_updates_handling_and_group_card tests/test_lead_handling_use_cases.py::test_comment_button_waits_for_next_message_and_saves_comment tests/test_lead_handling_use_cases.py::test_private_status_change_records_failed_event_when_group_edit_fails tests/test_lead_handling_use_cases.py::test_private_status_change_rejects_lead_owned_by_another_operator tests/test_lead_handling_use_cases.py::test_comment_text_rejects_lead_owned_by_another_operator -q`

Expected: FAIL because status/comment callbacks are not implemented.

- [ ] **Step 3: Implement status/comment callbacks**

Add callback data:

- `lh:open:<source_message_id>` - private lead card. This callback is
  implemented in Task 7 and must remain wired when status/comment actions are
  added.
- `lh:status:<source_message_id>:contacted`
- `lh:status:<source_message_id>:waiting`
- `lh:status:<source_message_id>:closed`
- `lh:comment:<source_message_id>`

When comment mode starts, store session:

```python
state="awaiting_comment"
payload={"source_message_id": str(source_message_id)}
```

On next private text, save comment event and clear session.

Ownership rule:

- For every private `open`, `status`, `comment`, and awaiting-comment text
  action, load the handling row and require
  `owner_telegram_user_id == actor.telegram_user_id`.
- If the lead is missing or owned by another operator, answer/send
  `Этот лид закреплен за другим оператором` and do not reveal text, mutate
  status, save comment, or edit the group card.
- Keep group callbacks separate: `Взял` is allowed on unowned leads, and
  `Не лид` remains allowed from the sales group according to Task 5.

After each status/comment, edit the original sales-group message if `sales_chat_id` and `sales_chat_message_id` are stored.

Telegram API failure behavior:

- If private `send_text` fails, record `callback_failed` or `message_failed`
  with `operation="send_private_message"` and log the exception.
- If private `edit_text` fails, record `callback_failed` with
  `operation="edit_private_message"` and log the exception.
- If group-card edit fails after status/comment save, keep the saved state and
  record `callback_failed` with `operation="edit_group_card"`.
- Never retry in a tight loop inside the callback handler. Let the operator
  press again or use a future repair tool.

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_lead_handling_use_cases.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/lead_handling/use_cases.py \
  backend/app/infrastructure/persistence/lead_handling_repository.py \
  backend/tests/test_lead_handling_use_cases.py
git commit -m "feat: update lead status and comments from telegram"
```

---

### Task 9: Runtime Integration And Safety Checks

**Files:**
- Modify: `backend/tests/test_notification_outbox.py`
- Modify: `backend/tests/test_worker_notifications.py`
- Modify: `docker-compose.yml`
- Modify: `state/current.md`

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
cd backend && uv run pytest \
  tests/test_notification_outbox.py \
  tests/test_notification_settings_api.py \
  tests/test_worker_notifications.py \
  tests/test_lead_handling_repository.py \
  tests/test_lead_handling_use_cases.py \
  tests/test_telegram_bot_worker.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run static checks for touched backend code**

Run:

```bash
cd backend && uv run ruff check app tests/test_notification_outbox.py tests/test_notification_settings_api.py tests/test_lead_handling_repository.py tests/test_lead_handling_use_cases.py tests/test_telegram_bot_worker.py
```

Expected: PASS.

Run:

```bash
cd backend && uv run mypy app
```

Expected: PASS or only pre-existing unrelated failures. If pre-existing failures appear, capture exact output in final notes and do not claim mypy is clean.

- [ ] **Step 3: Validate Compose config**

Run: `docker compose config >/tmp/pur-leads-compose.yml`

Expected: exit 0.

- [ ] **Step 4: Apply migrations in dev**

Run: `docker compose run --rm migrate`

Expected: Alembic upgrades to `0035_lead_handling_bot`.

- [ ] **Step 5: Restart affected services**

Run:

```bash
docker compose up -d backend notification-dispatcher lead-bot
```

Expected: services start successfully.

- [ ] **Step 6: Runtime smoke**

Run:

```bash
docker compose ps backend notification-dispatcher lead-bot
docker compose logs --since=90s notification-dispatcher lead-bot
```

Expected: no tracebacks; `lead-bot` either polls enabled interactive bots or reports no configured interactive routes.

- [ ] **Step 7: Update handoff**

Update `state/current.md`:

- mention lead handling bot tables and worker;
- mention whether interactive route is configured yet;
- mention verification commands and results;
- note that operators must `/start` the bot before private bot messages work.

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml state/current.md
git commit -m "chore: wire lead handling bot runtime"
```

---

## Final Verification Before Completion

Before reporting completion, run fresh:

```bash
cd backend && uv run pytest \
  tests/test_notification_outbox.py \
  tests/test_notification_settings_api.py \
  tests/test_worker_notifications.py \
  tests/test_lead_handling_repository.py \
  tests/test_lead_handling_use_cases.py \
  tests/test_telegram_bot_worker.py \
  -q
cd backend && uv run ruff check app tests/test_notification_outbox.py tests/test_notification_settings_api.py tests/test_lead_handling_repository.py tests/test_lead_handling_use_cases.py tests/test_telegram_bot_worker.py
docker compose config >/tmp/pur-leads-compose.yml
docker compose ps
docker compose logs --since=90s notification-dispatcher lead-bot
```

Report exact pass/fail status. Do not claim mypy/build/runtime is clean unless those commands were run and read.
