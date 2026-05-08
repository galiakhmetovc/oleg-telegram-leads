# Telegram Userbot Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Receive Telegram messages through a configured userbot account, run them through the existing enrichment worker, and send matched lead notifications through batched Telegram bot delivery.

**Architecture:** Keep the production pipeline durable and split by responsibility: userbot ingestion writes source messages and creates enrichment jobs; the existing worker enriches text; notification routing writes an outbox; a dedicated dispatcher batches and sends messages. Redis/Celery remains a task queue only, while Postgres stores the source messages, jobs, settings, and notification outbox.

**Tech Stack:** FastAPI, PostgreSQL, SQLAlchemy Core, Celery/Redis, Telethon, Telegram Bot API, React/MUI, Docker Compose dev services.

---

### Task 1: Durable Userbot Source Model

**Files:**
- Create: `backend/app/domain/telegram_ingestion.py`
- Create: `backend/app/application/telegram_ingestion/ports.py`
- Create: `backend/app/application/telegram_ingestion/use_cases.py`
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Create: `backend/app/infrastructure/persistence/telegram_ingestion_repository.py`
- Create: `backend/alembic/versions/0007_telegram_userbot_ingestion.py`
- Test: `backend/tests/test_telegram_ingestion_use_cases.py`

- [ ] Write failing tests for storing a new source message, deduplicating by source chat + Telegram message id, and publishing an enrichment job only for non-empty text.
- [ ] Implement domain DTOs and repository ports.
- [ ] Implement Postgres tables/repository and migration.
- [ ] Wire ingestion use case to existing `CreateEnrichmentJob`.

### Task 2: Interactive Userbot Login

**Files:**
- Create: `backend/app/infrastructure/telegram/userbot_login.py`
- Create: `backend/app/api/telegram_ingestion.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_telegram_ingestion_api.py`

- [ ] Write API tests for account create/update, masked API hash/session output, `send-code`, and `sign-in`.
- [ ] Implement Telethon `StringSession` login adapter based on old branch behavior.
- [ ] Expose settings and login endpoints under `/api/v1/settings/telegram-ingestion`.
- [ ] Preserve secrets when the UI sends empty secret fields.

### Task 3: Live Userbot Worker

**Files:**
- Create: `backend/app/infrastructure/telegram/userbot_listener.py`
- Create: `backend/app/cli/telegram_userbot_worker.py`
- Modify: `backend/pyproject.toml`
- Modify: `docker-compose.yml`

- [ ] Write unit tests around listener event conversion where feasible.
- [ ] Add Telethon dependency and a `userbot` compose service.
- [ ] Listen only to enabled source chats for authorized accounts.
- [ ] On new text/caption, call the ingestion use case and let normal worker queue process enrichment.

### Task 4: Batched Notification Outbox

**Files:**
- Modify: `backend/app/domain/notifications.py`
- Modify: `backend/app/application/notifications/ports.py`
- Modify: `backend/app/application/notifications/use_cases.py`
- Create: `backend/app/application/notifications/batching.py`
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Create: `backend/app/infrastructure/persistence/notification_outbox_repository.py`
- Create: `backend/app/cli/notification_dispatcher.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/alembic/versions/0007_telegram_userbot_ingestion.py`
- Test: `backend/tests/test_notification_outbox.py`

- [ ] Write failing tests for packing messages under Telegram `sendMessage` 4096-character limit.
- [ ] Write failing tests for "not later than 5 minutes" flushing and per-chat send spacing.
- [ ] Change enrichment completion from direct send to durable outbox enqueue.
- [ ] Add `notification-dispatcher` compose service to flush outbox periodically.

### Task 5: UI and Documentation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`
- Modify: `README.md`
- Modify: `state/current.md`

- [ ] Add settings UI for userbot accounts, source chats, sending code, and completing login.
- [ ] Add visible loading/progress state for Telegram settings actions.
- [ ] Document production flow, Telegram limits, StringSession secrecy, and why batch-runner is not connected to production notifications.
- [ ] Run backend and frontend checks.
