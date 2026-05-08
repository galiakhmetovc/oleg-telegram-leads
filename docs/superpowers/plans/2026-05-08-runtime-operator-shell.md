# Runtime Operator Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the operator UI with simple dev authentication, make Analytics the default live Telegram review surface, add notification links, and expose logs/system status.

**Architecture:** Keep v2 hexagonal boundaries: auth/session signing lives in `core` and API middleware, runtime analytics reads durable PostgreSQL state, notification templates receive explicit context, and frontend pages remain operator screens. Batch analytics remains historical tooling; the UI now defaults to a virtual live Telegram analytics run.

**Tech Stack:** FastAPI, PostgreSQL/SQLAlchemy, React/Vite/TypeScript/MUI, Docker Compose dev runtime.

---

### Task 1: Simple Auth

**Files:**
- Create: `backend/app/core/auth.py`
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Test: `backend/tests/test_auth_api.py`

- [ ] Add dev credentials to settings: `admin / pur-dev-password`.
- [ ] Add signed, expiring, HttpOnly session cookie.
- [ ] Protect `/api/v1/*` except auth endpoints; keep `/health` open.
- [ ] Add frontend login gate before loading protected data.

### Task 2: Live Telegram Analytics

**Files:**
- Modify: `backend/app/infrastructure/persistence/analytics_repository.py`
- Modify: `backend/app/api/analytics.py`
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Create: `backend/alembic/versions/0008_runtime_analytics_cleanup.py`
- Modify: `frontend/src/AnalyticsPage.tsx`
- Test: `backend/tests/test_analytics_api.py`, `frontend/src/App.test.tsx`

- [ ] Add virtual run `Telegram live` from Telegram source messages and enrichment results.
- [ ] Return source metadata, Telegram message link, app review link, and testing link.
- [ ] Clear old batch analytics tables in migration.
- [ ] Keep existing filter vocabulary using computed aggregates.

### Task 3: Notification Links

**Files:**
- Modify: `backend/app/application/notifications/routing.py`
- Modify: `backend/app/application/notifications/use_cases.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/infrastructure/persistence/telegram_ingestion_repository.py`
- Test: `backend/tests/test_notification_routing.py`

- [ ] Build notification context from source message by enrichment job id.
- [ ] Add `{telegram_message_url}` and `{app_message_url}` template fields.
- [ ] Append links even if an old route template does not include the fields.

### Task 4: Testing Deeplink

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/AnalyticsPage.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] Rename `Обогащение` to `Тестирование`.
- [ ] Open Analytics by default after auth.
- [ ] Add `#/testing?message_id=...` route that loads message text and starts enrichment.

### Task 5: Logs And System Status

**Files:**
- Create: `backend/app/api/runtime.py`
- Create: `backend/app/infrastructure/persistence/runtime_repository.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `backend/tests/test_runtime_api.py`, `frontend/src/App.test.tsx`

- [ ] Return recent durable events from enrichment events, source messages, notification outbox, and source chat errors.
- [ ] Return service status for backend, database, Redis, userbot sources, enrichment jobs, and notification outbox.
- [ ] Add `Логи` and `Статус системы` tabs.

### Task 6: Verification And Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `state/current.md`

- [ ] Run backend focused tests, then full backend verification feasible in current runtime.
- [ ] Run frontend tests and build.
- [ ] Update state and docs with auth, live analytics, links, logs, and system status.
