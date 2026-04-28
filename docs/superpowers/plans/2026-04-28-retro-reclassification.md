# Retro Reclassification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-run saved classified messages against the latest catalog classifier so catalog changes can produce retro leads in the web inbox.

**Architecture:** Keep the same lead classifier adapter and `LeadService` event/cluster path. Add a `reclassify_messages` runtime handler that defaults to `classification_statuses=["classified"]`, forces `detection_mode="retro_research"`, keeps messages marked classified, and suppresses Telegram notifications unless explicitly enabled.

**Tech Stack:** Python 3.12, SQLAlchemy, existing scheduler/runtime/lead services, pytest.

---

### Task 1: Runtime Retro Handler

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_lead_runtime_handlers.py`

- [x] Write failing tests for `reclassify_messages` reading classified messages, creating retro events/clusters, keeping Telegram web-only by default, and preserving message status.
- [x] Verify focused tests fail because the handler is not registered.
- [x] Refactor classification handling into a shared helper and add the `reclassify_messages` handler.
- [x] Run focused runtime tests and verify they pass.

### Task 2: Fuzzy Detection Mode Support

**Files:**
- Modify: `src/pur_leads/integrations/leads/fuzzy_classifier.py`
- Test: `tests/test_fuzzy_catalog_classifier.py`

- [x] Write a failing test that fuzzy classifier honors payload `detection_mode`.
- [x] Implement detection-mode selection with `live` default.
- [x] Run focused fuzzy tests and verify they pass.

### Task 3: Verification And Rollout

**Files:**
- Modify plan checklist only after verification.

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `node --check src/pur_leads/web/static/app.js`.
- [x] Run `TMPDIR=/home/admin/AI-AGENT/data/tmp/oleg-telegram-leads-pytest uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [x] Commit and push `main` (`3eae4b1`, follow-up cursor fix `0a72458`).
- [x] Deploy on `teamd-ams1`, restart worker/web if needed, verify `/health`, and enqueue initial retro reclassification.

### Task 4: Production-Safe Batch Chaining

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_lead_runtime_handlers.py`

- [x] Write a failing test that proves `reclassify_messages` chains to the next batch by cursor.
- [x] Add cursor filtering over `(message_date, telegram_message_id, source_message_id)`.
- [x] Load `limit + 1` messages to detect whether another batch is needed.
- [x] Enqueue the next `reclassify_messages` job with a stable idempotency key.
- [x] Verify focused runtime tests and full local verification.
- [x] Deploy `0a72458` to `teamd-ams1`, verify `/health`, and enqueue three source-scoped retro jobs with `limit=100`, low priority, and Telegram notifications disabled.
