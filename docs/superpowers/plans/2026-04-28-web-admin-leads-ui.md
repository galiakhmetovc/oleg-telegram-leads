# Web Admin And Leads UI Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable protected web slice for daily lead work: bootstrap admin login, Telegram-admin account authorization, task-backed `Take into work`, protected Leads Inbox APIs, and a compact operational Leads Inbox screen.

**Architecture:** Keep FastAPI thin over existing services. Web auth stores users/sessions in SQLite and uses signed, HTTP-only session cookies; all UI actions call service methods so Telegram remains an urgent notification channel, not the work UI. The first UI is a restrained operational workspace: left queue, right detail/action panel, no marketing page.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, SQLite, pytest/TestClient, stdlib password/session crypto, plain HTML/CSS/JS served by FastAPI.

---

## Visual Direction

- Visual thesis: dense, calm operator console for leads and support work, with neutral surfaces and one restrained accent for action state.
- Content plan: login screen, Leads Inbox queue/detail workspace, action controls, and a compact Settings/Admin screen for Telegram admin accounts/settings.
- Interaction thesis: queue selection updates detail without page reload; action buttons give immediate status feedback; compact filters keep the workspace scannable.

## Scope

This is an incremental execution slice, not the whole first-production spec. It assumes the existing catalog source, Telegram ingestion, and Lead Inbox backend foundations are already implemented. Follow-up implementation plans still need to cover full catalog UI, source onboarding UI, CRM memory/conversion wizard, Today/tasks overview, notification delivery/policy UI, quality/evaluation dashboards, archive/backup operations, and richer operational logs.

This slice intentionally does not implement full CRM entities, rich catalog editors, Telegram notification delivery, password reset email, or scoped roles beyond `admin`. It does implement the parts required for the first protected Leads Inbox to be usable and auditable.

## Task 1: Web Auth And Task Schema

- [x] Implement web auth/task migration and model definitions.

**Files:**
- Create: `migrations/versions/0005_web_auth_foundation.py`
- Create: `src/pur_leads/models/web_auth.py`
- Create: `src/pur_leads/models/tasks.py`
- Test: `tests/test_web_auth_migration.py`

- [ ] Add `web_users` with Telegram and local auth fields from the spec.
- [ ] Add `web_auth_sessions` with hashed session tokens, expiry, last seen, and revoke fields.
- [ ] Add `tasks` with `lead_cluster_id`, `lead_event_id`, client/opportunity/support/contact-reason links, status, priority, due date, owner/assignee, and completion fields.
- [ ] Add indexes for `local_username`, `telegram_user_id`, and session token lookup.
- [ ] Verify role/status/auth/task constraints and session token uniqueness.

Completed: added `web_users`, `web_auth_sessions`, and `tasks` schema/model files with
identity indexes and role/status/session/task constraints. Covered by `tests/test_web_auth_migration.py`.

## Task 2: Auth Service

- [x] Implement auth/task services and task-backed `take_into_work`.

**Files:**
- Create: `src/pur_leads/repositories/web_auth.py`
- Create: `src/pur_leads/services/web_auth.py`
- Create: `src/pur_leads/repositories/tasks.py`
- Create: `src/pur_leads/services/tasks.py`
- Modify: `src/pur_leads/services/leads.py`
- Modify: `src/pur_leads/core/config.py`
- Test: `tests/test_web_auth_service.py`
- Test: `tests/test_lead_work_actions.py`

- [ ] Implement stdlib PBKDF2 password hashing and constant-time verification.
- [ ] Implement `ensure_bootstrap_admin(username, password)` creating local `admin` with `must_change_password=true`.
- [ ] Implement local login that rejects disabled/pending users and creates a hashed session token.
- [ ] Implement session validation, touch, revoke/logout, and password change.
- [ ] Implement Telegram login payload verification using bot token secret material, mapped to pre-approved `web_users.telegram_user_id`.
- [ ] Implement adding Telegram admin accounts from an existing admin context.
- [ ] Implement `take_into_work` as a service action: set cluster `in_work`/`confirmed`, write `lead_confirmed`, create a due-now contact task, store it in `lead_clusters.primary_task_id`, and do not create CRM records.
- [ ] Record audit events for login success, denied login, logout, password change, and user creation.

Completed: added PBKDF2 password hashing, local/bootstrap auth, Telegram payload verification,
session lifecycle, Telegram admin creation, disabled-user handling, task creation service, and
task-backed `LeadService.take_into_work`. Covered by `tests/test_web_auth_service.py` and
`tests/test_lead_work_actions.py`.

## Task 3: Web App Dependencies And Auth Routes

- [x] Implement web app DB dependencies and auth routes.

**Files:**
- Create: `src/pur_leads/web/dependencies.py`
- Create: `src/pur_leads/web/routes_auth.py`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_web_auth_routes.py`

- [ ] Add app state for engine/session factory and request-scoped DB sessions.
- [ ] Add current-admin dependency reading `pur_session` HTTP-only cookie.
- [ ] Add `POST /api/auth/local`, `POST /api/auth/telegram`, `POST /api/auth/logout`, and `GET /api/me`.
- [ ] Add `POST /api/auth/change-password`; force bootstrap users with `must_change_password=true` into this flow before normal app access.
- [ ] Set secure cookie attributes configurable for local/dev vs production.
- [ ] Verify unauthenticated API calls return `401`, login sets cookie, password-change clears `must_change_password`, logout revokes session, and unknown Telegram users are denied.
- [ ] Verify Telegram auth payload hash/signature using test bot token fixtures, not a placeholder.

Completed: added app DB/session state, current-admin dependency, local/Telegram login routes,
logout, `/api/me`, password change, cookie handling, and bootstrap admin app initialization.
Covered by `tests/test_web_auth_routes.py`.

## Task 4: Leads Inbox API

- [x] Implement protected Leads Inbox API.

**Files:**
- Create: `src/pur_leads/web/routes_leads.py`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_web_leads_routes.py`

- [x] Add `GET /api/leads` backed by `LeadInboxService.list_cluster_queue`.
- [x] Add `GET /api/leads/{cluster_id}` backed by `LeadInboxService.get_cluster_detail`.
- [x] Add `POST /api/leads/{cluster_id}/actions` backed by `LeadService`/task services, with route-level mapping from UI names like `take_into_work` to internal actions.
- [x] Add payload validation for `not_lead` reason codes, snooze date, duplicate target, context-only event id, and correction target ids.
- [x] Add narrow feedback endpoints/payloads for cluster, event, match, term, item, category, sender, and message targets.
- [x] Support filters for status, source, category, retro, maybe, `auto_pending`, operator issues, and min confidence.
- [x] Verify protected access, response shape, task-backed take-into-work, reason-required not-lead, maybe, snooze, duplicate, context-only, wrong category/item/term, term-too-broad, and commercial outcome persistence.
- [x] Verify commercial outcomes use `feedback_scope=crm_outcome` and `learning_effect=no_classifier_learning`.

Completed: added protected Leads Inbox queue/detail routes, task-backed lead actions,
generic and target-scoped feedback routes, operator-issue filters, action payload validation,
feedback target existence validation, feedback enum allow-lists, and route tests covering
queue/detail, take-into-work, not-lead, maybe, snooze, duplicate, context-only, correction
validation, target-scoped feedback, auth guards, and commercial outcome defaults.

## Task 5: Admin Settings/User API

**Files:**
- Create: `src/pur_leads/web/routes_admin.py`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_web_admin_routes.py`

- [ ] Add `GET /api/admin/users` for current admin users.
- [ ] Add `POST /api/admin/users/telegram` to add Telegram admin accounts.
- [ ] Add `PATCH /api/admin/users/{user_id}` for status/display name updates.
- [ ] Add `GET /api/settings` and `PUT /api/settings/{key}` over existing `SettingsService`.
- [ ] Write audit rows for settings updates, admin user creation, status changes, denied admin actions, and session revocation after user disable.
- [ ] Write audit rows for protected-route authorization denials and future role-change/status-change events.
- [ ] Verify settings revisions/audit rows are created, disabled users cannot authenticate, denied protected-route access is audited, and disabling a user revokes active sessions.

## Task 6: First Leads Inbox Screen

**Files:**
- Create: `src/pur_leads/web/routes_pages.py`
- Create: `src/pur_leads/web/static/app.css`
- Create: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_web_pages.py`

- [ ] Serve `/login` with local admin form, forced password-change state, and real Telegram Login payload submission hook.
- [ ] Serve `/` as the protected Leads Inbox workspace with queue, filters, detail/timeline, match evidence, feedback, and actions.
- [ ] Serve `/admin` as a compact protected Settings/Admin screen for Telegram admin accounts and editable settings in this slice.
- [ ] Keep the UI dense and operational: no landing hero, no marketing copy, no nested cards.
- [ ] Use progressive enhancement: HTML renders shell, JS fetches `/api/leads` and updates detail/action states.
- [ ] Display source chat/link, sender, detection modes, retro date/trigger, classifier versions, merge reasons/actions, CRM candidates count, previous feedback, `auto_pending`, `retro`, `maybe`, and auto-merge/correction markers.
- [ ] Verify protected redirect/login behavior, static asset availability, and UI JSON rendering for the required detail fields.

## Task 7: CLI/Web Runtime Wiring

**Files:**
- Modify: `src/pur_leads/cli.py`
- Modify: `src/pur_leads/web/app.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_app_health.py`

- [ ] Add bootstrap admin env/config handling for `pur-leads web`.
- [ ] Ensure app startup can initialize auth tables after migrations are run.
- [ ] Keep `worker once` on the canonical runtime path; do not create a separate web worker loop.
- [ ] Verify existing health and CLI tests remain green.

## Acceptance

Run:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check
uv run --extra dev ruff format --check
uv run --extra dev mypy src
docker compose config
```

Manual smoke after implementation:

```bash
uv run pur-leads db upgrade
uv run pur-leads web
```

Open `http://127.0.0.1:8000/login`, log in as bootstrap admin, open Leads Inbox, apply a test action to a seeded cluster, and confirm the detail pane updates.
