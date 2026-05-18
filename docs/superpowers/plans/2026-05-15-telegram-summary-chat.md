# Telegram Summary Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send day/night Telegram operational summaries to a dedicated chat.

**Architecture:** Store summary destination and schedule in existing notification settings JSON, and add a durable `notification_summary_runs` table for idempotency. A small polling CLI computes the latest completed Moscow day/night period, collects runtime metrics from PostgreSQL/Redis, sends one Telegram message, and records the result.

**Tech Stack:** FastAPI/Pydantic settings API, SQLAlchemy/Alembic/PostgreSQL, Redis queue checks, existing Telegram Bot API sender, Docker Compose worker service.

---

### Task 1: Settings Model

**Files:**
- Modify: `backend/app/domain/notifications.py`
- Modify: `backend/app/infrastructure/persistence/notification_settings_repository.py`
- Modify: `backend/app/api/notifications.py`
- Test: `backend/tests/test_notification_settings_api.py`

- [ ] Add `NotificationSummarySettings` with `enabled`, `bot_id`, `chat_id`, `timezone`, `day_start_hour`, and `night_start_hour`.
- [ ] Add optional `summary` to `NotificationSettings`.
- [ ] Round-trip `summary` through persistence/API while preserving backward compatibility when config lacks it.
- [ ] Validate summary bot/chat references and enabled bot token requirements.

### Task 2: Summary Scheduling And Rendering

**Files:**
- Create: `backend/app/application/notifications/summary.py`
- Test: `backend/tests/test_notification_summary.py`

- [ ] Write failing tests for Moscow day period `09:00-21:00` and night period `21:00-09:00`.
- [ ] Write failing tests for one-send idempotency through a fake run repository.
- [ ] Implement period selection, message rendering, and `SendNotificationSummary`.

### Task 3: Metrics Repository And Idempotency

**Files:**
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Create: `backend/app/infrastructure/persistence/notification_summary_repository.py`
- Create: `backend/alembic/versions/0036_notification_summary_runs.py`
- Test: `backend/tests/test_notification_summary_repository.py`

- [ ] Write failing repository tests for claiming a period once.
- [ ] Write failing repository tests for message, source, lead-temperature, job, LLM, outbox, and Redis queue metrics.
- [ ] Implement SQLAlchemy table metadata, Alembic migration, repository SQL, and queue depth reads.

### Task 4: Runtime Wiring

**Files:**
- Create: `backend/app/cli/notification_summary_worker.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [ ] Add CLI loop with `--interval`.
- [ ] Add Compose service `summary-bot`.
- [ ] Document that summaries go through the existing Telegram bot/chat settings.

### Task 5: Verification

**Files:**
- Run focused backend tests.
- Run Ruff on changed backend files.
- Run `docker compose config`.

- [ ] Fix failures only in touched/new code.
- [ ] Report any unrelated pre-existing failures separately.
