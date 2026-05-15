# Telegram Lead Handling Bot Design

## Goal

Add a Telegram-only lead handling workflow after the system detects a lead and
sends it to the sales group. Operators do not need web access. They claim,
review, comment on, and update their leads through Telegram bot buttons and
private chat with the bot.

## Product Shape

The existing deterministic/LLM lead detection remains responsible for deciding
whether a Telegram source message is a lead. The new workflow starts only after a
lead notification is created.

There are two Telegram surfaces:

- Sales group: receives one interactive lead card per lead.
- Private bot chat: lets an operator see and update leads they claimed.

The web UI remains an admin/operator analytics surface. It is not the primary
workspace for sales operators, and this slice does not add web roles or web user
management for them.

## Sales Group Flow

Interactive sales notifications are not batched. One lead becomes one Telegram
message so buttons and replies are unambiguous.

The lead card includes:

- source chat title and Telegram message link when available;
- short source text preview;
- score, temperature, and review lane;
- short reason list;
- current handling status;
- current owner, if claimed.

Initial buttons:

- `Взял`
- `Не лид`

When a manager presses `Взял`, the bot:

- creates or updates the handling row for the source message;
- sets status to `claimed`;
- stores the Telegram actor id, username, and display name from the callback;
- stores the sales-group message id;
- records an event;
- edits the original group message to show `Взял: @username`.

When a manager presses `Не лид`, the bot:

- sets handling status to `not_lead`;
- stores the Telegram actor identity;
- records an event;
- writes `message_reviews.verdict = not_lead` for the source message;
- cancels unsent notifications for the same source message when applicable;
- edits the original group message to show `Не лид: @username`.

## Private Bot Flow

Operators must open the bot and press `/start` before the bot can message them
privately. This is a Telegram platform constraint.

Private menu:

- `Мои лиды`
- `Новые`
- `В работе`
- `Закрытые`

`Мои лиды` lists leads where `owner_telegram_user_id` equals the current
Telegram user id. Each row shows a compact title, source, status, and last
update time.

Opening a lead shows:

- source and source-message link;
- lead text preview;
- current status;
- owner;
- last comment;
- buttons for status/comment actions.

Private lead actions:

- change status;
- add comment;
- reopen if needed;
- open source message.

The first minimal status set is:

- `claimed`
- `contacted`
- `waiting`
- `closed`
- `not_lead`

The group card should be edited after private status/comment changes so the
sales group sees the latest state without opening the web app.

## Storage

Add `lead_handlings`:

- `id`
- `source_message_id`
- `notification_outbox_id`
- `sales_chat_id`
- `sales_chat_message_id`
- `status`
- `owner_telegram_user_id`
- `owner_telegram_username`
- `owner_display_name`
- `last_comment`
- `claimed_at`
- `closed_at`
- `created_at`
- `updated_at`

Add `lead_handling_events`:

- `id`
- `lead_handling_id`
- `source_message_id`
- `actor_telegram_user_id`
- `actor_telegram_username`
- `actor_display_name`
- `event_type`
- `payload`
- `created_at`

Event types:

- `created`
- `claimed`
- `marked_not_lead`
- `status_changed`
- `comment_added`
- `group_message_edited`
- `callback_failed`

The handling row is the current state. Events are the audit trail.

## Notification Changes

Existing notification routes can stay batched for ordinary digests. Add a route
mode for interactive lead handling cards:

- batched route: existing behavior;
- interactive route: sends each outbox item separately with an inline keyboard.

Interactive routes require `source_message_id`. If the route matches a manual
Testing job without a source message, the dispatcher should fail that outbox item
with a clear configuration error instead of sending an unusable button card.

The Telegram sender needs support for:

- `sendMessage` with `reply_markup.inline_keyboard`;
- `editMessageText`;
- `answerCallbackQuery`.

## Bot Updates

Run a dedicated bot update worker or webhook endpoint for callback queries and
private messages. For dev simplicity, polling is acceptable. For production, the
same application service should work behind either polling or webhook delivery.

Callback data must be short and opaque, for example:

- `lh:claim:<handling_id>`
- `lh:notlead:<handling_id>`
- `lh:status:<handling_id>:waiting`
- `lh:comment:<handling_id>`

The backend must validate that the handling id exists and that the callback came
from Telegram, not from a forged web request. Bot token authentication covers the
Telegram API side; if webhook is used, the secret token header should also be
validated.

## Error Handling

Telegram API errors are stored in handling events and visible in runtime logs.

Expected cases:

- bot cannot DM operator because `/start` was not used yet;
- callback arrives for an old/deleted lead card;
- group message edit fails because the message is too old or missing;
- duplicate button presses race;
- Telegram rate limits.

Duplicate `Взял` presses should be deterministic:

- if the lead is unowned, first callback wins;
- if the same owner presses again, return the current state;
- if another user presses after claim, answer callback with `Уже взял @owner`
  and do not overwrite owner.

`Не лид` can override an unclaimed lead. If a lead is already claimed, the first
MVP should still allow `Не лид` but record who marked it. If this becomes noisy,
later add an admin-only or owner-only rule.

## MVP

The first implementation should include only:

- interactive non-batched sales notifications;
- group buttons `Взял` and `Не лид`;
- persisted handling state and events;
- group message edit after button press;
- `message_reviews.not_lead` update when `Не лид` is pressed;
- private `/start` and `Мои лиды`;
- private lead card with status change and comment.

Do not implement:

- web user roles;
- assignment from web;
- automatic first outreach to the external lead;
- userbot DM sending;
- Telegram group creation with the lead.

Those can be added later once the basic sales handling loop works.

## Testing

Backend tests should cover:

- interactive notification route creates one Telegram message per lead;
- interactive route includes inline buttons tied to one source message;
- `Взял` creates handling state, records event, and edits the group message;
- second `Взял` from another user does not overwrite owner;
- `Не лид` writes handling state and `message_reviews.not_lead`;
- private `Мои лиды` only lists leads owned by the requesting Telegram user;
- private comment action records an event and updates `last_comment`;
- Telegram sender surfaces send/edit/callback errors as failed events/logs.
