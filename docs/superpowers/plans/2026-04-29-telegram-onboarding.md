# Telegram Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authenticated onboarding flow that configures Telegram bot notifications, notification group discovery, userbot session upload, interactive userbot login, and first-source setup guidance.

**Architecture:** Build the flow on the existing web app, `settings`, `secret_refs`, `userbot_accounts`, and `monitored_sources`. Store secret values in local files referenced by `secret_refs`, expose only masked/status data in the UI, and make worker/web runtime read Telegram credentials from settings-backed secret references with env fallbacks for development.

**Tech Stack:** FastAPI, SQLAlchemy, Telethon, httpx, SQLite, vanilla HTML/CSS/JS.

---

### Task 1: Secret Storage And Runtime Credential Resolution

**Files:**
- Modify: `src/pur_leads/services/secrets.py`
- Modify: `src/pur_leads/core/config.py`
- Modify: `src/pur_leads/cli.py`
- Modify: `src/pur_leads/web/dependencies.py`
- Test: `tests/test_secret_refs.py`

- [x] Write failing tests for storing a local secret file with `0600`, resolving a setting-backed secret, and keeping public payloads masked.
- [x] Implement `SecretRefService.create_local_secret()` and `resolve_value()`.
- [x] Add config paths for local secret storage and Telegram session storage.
- [x] Update worker/web credential lookup to prefer setting-backed secret refs and keep env fallback.

### Task 2: Onboarding API

**Files:**
- Create: `src/pur_leads/integrations/telegram/bot_setup.py`
- Create: `src/pur_leads/integrations/telegram/userbot_login.py`
- Create: `src/pur_leads/web/routes_onboarding.py`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_web_onboarding_routes.py`

- [x] Write failing route tests for onboarding status, bot token validation, notification group discovery, notification test/save, session-file userbot setup, and interactive userbot login.
- [x] Implement Bot API setup client using `getMe`, `getUpdates`, and `sendMessage`.
- [x] Implement route handlers with injectable transports/factories for tests.
- [x] Implement interactive Telethon login as start/complete with in-memory pending attempts.

### Task 3: Onboarding UI

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [x] Write failing page tests for `/onboarding`, Russian embedded docs, and JS endpoints.
- [x] Add protected `/onboarding` page with checklist and forms.
- [x] Add JS for bot token, group discovery/test, session upload, interactive login, and first source link.
- [x] Redirect after local login/password change to onboarding while setup is incomplete.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`
- Modify: `README.md`

- [x] Document the onboarding flow and secret handling.
- [x] Run focused tests, `ruff`, JS syntax check, and full pytest.
- [ ] Commit, push, deploy, and verify remote health plus onboarding page.
