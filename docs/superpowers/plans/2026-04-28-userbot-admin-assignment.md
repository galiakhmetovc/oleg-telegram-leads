# Userbot Admin And Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add web-managed Telegram userbot accounts and assign new monitored sources to the configured/default active userbot so Telegram jobs serialize correctly.

**Architecture:** Keep userbot accounts in the existing `userbot_accounts` table. Add a small repository/service/API layer, expose it from the existing Admin workspace, and make `TelegramSourceService.create_draft` pick the explicit `telegram_default_userbot_account_id` setting or the first active userbot. This stays in the canonical scheduler/worker path; no separate Telegram loop is introduced.

**Tech Stack:** Python 3.12, SQLAlchemy Core, FastAPI, existing static HTML/CSS/JS, pytest.

---

### Task 1: Userbot Repository And Service

**Files:**
- Create: `src/pur_leads/repositories/userbots.py`
- Create: `src/pur_leads/services/userbots.py`
- Modify: `src/pur_leads/services/settings.py`
- Test: `tests/test_userbot_service.py`

- [x] Write failing tests for creating/listing userbots, selecting configured default, falling back to first active userbot, and auditing changes.
- [x] Run `uv run --extra dev pytest tests/test_userbot_service.py -q` and verify expected failures.
- [x] Implement userbot repository/service with safe public payloads and `select_default_userbot`.
- [x] Add default settings for `telegram_default_userbot_account_id`, `telegram_flood_sleep_threshold_seconds`, and `telegram_get_history_wait_seconds`.
- [x] Run `uv run --extra dev pytest tests/test_userbot_service.py -q` and verify it passes.
- [x] Commit as `feat: add userbot account service`.

### Task 2: Source Assignment

**Files:**
- Modify: `src/pur_leads/services/telegram_sources.py`
- Test: `tests/test_telegram_source_service.py`

- [x] Write failing tests proving new sources inherit the default active userbot and queued source jobs carry `userbot_account_id`.
- [x] Run `uv run --extra dev pytest tests/test_telegram_source_service.py -q` and verify expected failures.
- [x] Update source creation to assign the selected default userbot when available.
- [x] Run `uv run --extra dev pytest tests/test_telegram_source_service.py -q` and verify it passes.
- [x] Commit as `feat: assign sources to default userbot`.

### Task 3: Admin API And UI

**Files:**
- Modify: `src/pur_leads/web/routes_admin.py`
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Test: `tests/test_web_admin_routes.py`
- Test: `tests/test_web_pages.py`

- [ ] Write failing API tests for auth-required `/api/admin/userbots` list/create.
- [ ] Write failing page/static tests proving Admin renders userbot controls and JS calls `/api/admin/userbots`.
- [ ] Run `uv run --extra dev pytest tests/test_web_admin_routes.py tests/test_web_pages.py -q` and verify expected failures.
- [ ] Implement protected userbot API routes and Admin workspace controls.
- [ ] Run `uv run --extra dev pytest tests/test_web_admin_routes.py tests/test_web_pages.py -q` and verify it passes.
- [ ] Commit as `feat: add userbot admin UI`.

### Task 4: Full Verification And Deploy

- [ ] Run `uv run --extra dev ruff check`.
- [ ] Run `uv run --extra dev ruff format --check`.
- [ ] Run `uv run --extra dev mypy src`.
- [ ] Run `uv run --extra dev pytest -q`.
- [ ] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [ ] Push `main`.
- [ ] SSH to `teamd-ams1`, pull fast-forward, rebuild web, run migrations if needed, restart `web`, and verify `/health` and `/admin`.
