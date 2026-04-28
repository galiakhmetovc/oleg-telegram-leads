# Source Onboarding Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add web-managed Telegram source onboarding: create sources, queue access checks/previews, activate/pause sources, inspect preview/checkpoint state, and keep Telegram as notification-only.

**Architecture:** Reuse the existing `monitored_sources`, access-check worker, preview worker, polling worker, and scheduler. The web layer only mutates source config and enqueues jobs; actual Telegram IO remains in the canonical worker/runtime path.

**Tech Stack:** Python 3.12, SQLAlchemy Core, FastAPI, SQLite, existing static HTML/CSS/JS, pytest.

---

### Task 1: Source Repository And Service Controls

**Files:**
- Modify: `src/pur_leads/repositories/telegram_sources.py`
- Modify: `src/pur_leads/services/telegram_sources.py`
- Test: `tests/test_telegram_source_service.py`

- [x] Write failing tests for listing sources, reading detail with preview rows, requesting access check jobs, requesting preview jobs, activating only `preview_ready` sources from web, and pausing active sources.
- [x] Run `uv run --extra dev pytest tests/test_telegram_source_service.py -q` and verify expected failures.
- [x] Add repository list/detail helpers for source rows, recent access checks, preview messages, and source-related scheduler jobs.
- [x] Add service methods `list_sources`, `get_source_detail`, `request_access_check`, `request_preview`, `activate_from_web`, and `pause`.
- [x] Run `uv run --extra dev pytest tests/test_telegram_source_service.py -q` and verify it passes.
- [x] Commit as `feat: add source onboarding service controls`.

### Task 2: Source Web API

**Files:**
- Create: `src/pur_leads/web/routes_sources.py`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_web_source_routes.py`

- [x] Write failing tests for auth-required source list/create/detail.
- [x] Write failing tests for check-access, preview, activate, pause, and reset-checkpoint endpoints.
- [x] Run `uv run --extra dev pytest tests/test_web_source_routes.py -q` and verify expected route failures.
- [x] Implement protected `/api/sources` routes and JSON payloads.
- [x] Run `uv run --extra dev pytest tests/test_web_source_routes.py -q` and verify it passes.
- [x] Commit as `feat: add source onboarding api`.

### Task 3: Source Web Workspace

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [x] Write failing page tests proving `/sources` is protected and linked from topbar.
- [x] Run `uv run --extra dev pytest tests/test_web_pages.py -q` and verify expected failures.
- [x] Add `/sources` page with source create form, queue list, detail pane, status badges, preview messages, and action buttons.
- [x] Run `uv run --extra dev pytest tests/test_web_pages.py -q` and verify it passes.
- [x] Commit as `feat: add source onboarding workspace`.

### Task 4: Full Verification And Deploy

- [ ] Run `uv run --extra dev ruff check`.
- [ ] Run `uv run --extra dev ruff format --check`.
- [ ] Run `uv run --extra dev mypy src`.
- [ ] Run `uv run --extra dev pytest -q`.
- [ ] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [ ] Push `main`.
- [ ] SSH to `teamd-ams1`, pull fast-forward, rebuild web, run migrations if needed, restart `web`, and verify `/health` and `/sources`.
