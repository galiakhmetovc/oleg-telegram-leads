# Telegram Source Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Telegram source-management and message-ingestion layer on top of the greenfield foundation.

**Architecture:** Keep Telegram as one canonical runtime path: configured sources in SQLite, scheduler jobs for bounded work, one active userbot worker by default, and `source_messages.id` as the canonical FK for monitored Telegram messages. Web/API commands can create sources later, but the ingestion layer must already enforce access status, checkpoints, idempotency, and audit/operational events.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, Telethon, pytest, pytest-asyncio, existing scheduler/settings/audit/secrets foundation.

---

## Scope

This plan implements only Telegram source and message ingestion. It does not implement AI lead classification, catalog extraction, CRM, or web UI screens.

## Task 1: Telegram Source Schema

- [x] Implement migration/model tables and verify with migration tests.

**Files:**
- Create: `migrations/versions/0002_telegram_sources.py`
- Create: `src/pur_leads/models/telegram_sources.py`
- Test: `tests/test_telegram_source_migration.py`

Tables:

- `userbot_accounts`
- `monitored_sources`
- `source_access_checks`
- `source_preview_messages`
- `source_messages`
- `sender_profiles`
- `message_context_links`

Key rules:

- `source_messages.id` is canonical for monitored messages.
- `source_messages.raw_source_id` is optional and points to future raw `sources.id`.
- unique message identity is `(monitored_source_id, telegram_message_id)`.
- source checkpoints live on `monitored_sources`.
- archived message retention keeps identity rows.

Verification:

```bash
uv run --extra dev pytest tests/test_telegram_source_migration.py -q
```

## Task 2: Source Repository And Service

- [x] Implement source repository/service and verify source lifecycle tests.

**Files:**
- Create: `src/pur_leads/repositories/telegram_sources.py`
- Create: `src/pur_leads/services/telegram_sources.py`
- Test: `tests/test_telegram_source_service.py`

Behaviors:

- create draft source from username/link/message link;
- assign purpose: `lead_monitoring`, `catalog_ingestion`, `both`;
- default live lead-monitoring sources to `start_mode = from_now`;
- transition `draft -> checking_access -> preview_ready -> active`;
- checkpoint reset requires explicit confirmation flag;
- source changes create audit records.

## Task 3: Telegram Client Port

- [x] Define Telegram client protocol and DTOs; verify with fake client tests.

**Files:**
- Create: `src/pur_leads/integrations/telegram/client.py`
- Create: `src/pur_leads/integrations/telegram/types.py`
- Test: `tests/test_telegram_client_port.py`

Define a protocol/interface around Telethon:

- resolve source input;
- check access;
- fetch preview messages;
- fetch bounded message batch after checkpoint;
- fetch reply/neighbor context;

Tests use fake clients. Do not require live Telegram access.

## Task 4: Source Access And Preview Jobs

- [x] Implement access/preview jobs and verify with fake Telegram client tests.

**Files:**
- Create: `src/pur_leads/workers/telegram_access.py`
- Test: `tests/test_telegram_access_jobs.py`

Behaviors:

- `check_source_access` job writes `source_access_checks`;
- access success sets `preview_ready`;
- access failures set `needs_join`, `needs_captcha`, `private_or_no_access`, `flood_wait`, `banned`, or `read_error`;
- operator-required failures create `operational_events`;
- preview stores text/caption samples without downloading attachments and without moving live checkpoint.

## Task 5: Polling And Message Persistence

**Files:**
- Create: `src/pur_leads/workers/telegram_polling.py`
- Test: `tests/test_telegram_polling_jobs.py`

Behaviors:

- `poll_monitored_source` fetches bounded batches only for `active` sources;
- stores text, captions, sender metadata, reply/thread/forward metadata;
- deduplicates by `(monitored_source_id, telegram_message_id)`;
- updates checkpoint after successful batch;
- records checkpoint before/after in `scheduler_jobs`;
- no attachment downloads for monitoring sources.

## Task 6: Context Fetching

**Files:**
- Create: `src/pur_leads/workers/message_context.py`
- Test: `tests/test_message_context_jobs.py`

Behaviors:

- fetch explicit reply parent/ancestor links;
- fetch configured neighboring messages before/after;
- store links in `message_context_links`;
- context jobs are idempotent per message/context window.

## Task 7: Runtime Worker Loop

**Files:**
- Create: `src/pur_leads/workers/runtime.py`
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_worker_runtime.py`

Behaviors:

- `pur-leads worker once` executes one due job through registered handlers;
- Telegram jobs remain serialized per userbot through scheduler acquisition;
- unsupported job types fail with visible operational event;
- worker never runs an infinite loop in tests.

## Acceptance

Run:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src
docker compose config
```

Manual/live Telegram login remains outside this plan unless credentials and session setup are explicitly provided through `secret_refs`.
