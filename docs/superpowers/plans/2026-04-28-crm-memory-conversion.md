# CRM Memory Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first practical CRM memory layer: clients, contacts, objects, interests, assets, opportunities, support cases, contact reasons, touchpoints, and explicit lead-cluster conversion.

**Architecture:** Keep CRM as normal SQLite tables and focused services behind the existing FastAPI/runtime path. Lead `Take into work` remains task-only; explicit conversion creates CRM records, writes `crm_conversion_actions`, and marks the cluster converted only when a primary CRM/work entity exists.

**Tech Stack:** Python 3.12, SQLAlchemy Core, Alembic, FastAPI, SQLite, pytest, existing static HTML/CSS/JS.

---

### Task 1: CRM Schema Foundation

**Files:**
- Create: `migrations/versions/0006_crm_memory.py`
- Create: `src/pur_leads/models/crm.py`
- Modify: `src/pur_leads/models/__init__.py`
- Test: `tests/test_crm_migration.py`

- [x] Write a failing migration test proving all CRM tables and key indexes exist after `upgrade_database`.
- [x] Run `uv run --extra dev pytest tests/test_crm_migration.py -q` and verify it fails because CRM tables do not exist.
- [x] Implement migration/model definitions for `clients`, `contacts`, `client_objects`, `client_interests`, `client_assets`, `opportunities`, `support_cases`, `contact_reasons`, and `touchpoints`.
- [x] Include enum check constraints matching the source-of-truth spec and foreign keys to lead/catalog/task/auth tables where available.
- [x] Run `uv run --extra dev pytest tests/test_crm_migration.py -q` and verify it passes.
- [x] Commit as `feat: add crm memory schema`.

### Task 2: CRM Repository And Manual Service

**Files:**
- Create: `src/pur_leads/repositories/crm.py`
- Create: `src/pur_leads/services/crm.py`
- Test: `tests/test_crm_service.py`

- [ ] Write failing tests for manual client creation with contact, object, interest, asset, contact reason, and touchpoint records.
- [ ] Write failing tests for duplicate hints by Telegram user id, username, phone, and email.
- [ ] Run `uv run --extra dev pytest tests/test_crm_service.py -q` and verify failures are missing CRM service/repository behavior.
- [ ] Implement repository dataclasses and CRUD/list/detail helpers.
- [ ] Implement `CrmService.create_client_profile`, related-record creation, duplicate hint lookup, and audit entries.
- [ ] Run `uv run --extra dev pytest tests/test_crm_service.py -q` and verify it passes.
- [ ] Commit as `feat: add crm memory service`.

### Task 3: Lead Cluster CRM Conversion

**Files:**
- Modify: `src/pur_leads/services/crm.py`
- Modify: `src/pur_leads/repositories/leads.py`
- Test: `tests/test_crm_conversion_service.py`

- [ ] Write failing tests proving explicit conversion can create `client + contact + object + interest + task`, record a `crm_conversion_actions` row, and update the lead cluster to `converted`.
- [ ] Write failing tests proving conversion refuses unknown clusters and duplicate contacts unless `link_existing_client_id` is provided.
- [ ] Run `uv run --extra dev pytest tests/test_crm_conversion_service.py -q` and verify expected failures.
- [ ] Implement `CrmService.convert_lead_cluster` with duplicate guard, optional existing-client link, and transaction-safe updates.
- [ ] Ensure `Take into work` still creates no CRM conversion action.
- [ ] Run `uv run --extra dev pytest tests/test_crm_conversion_service.py tests/test_lead_work_actions.py -q`.
- [ ] Commit as `feat: convert lead clusters into crm memory`.

### Task 4: CRM API Routes

**Files:**
- Create: `src/pur_leads/web/routes_crm.py`
- Modify: `src/pur_leads/web/app.py`
- Modify: `src/pur_leads/web/routes_leads.py`
- Test: `tests/test_web_crm_routes.py`

- [ ] Write failing route tests for auth-required list/create/detail of clients.
- [ ] Write failing route tests for `/api/leads/{cluster_id}/crm/convert`.
- [ ] Run `uv run --extra dev pytest tests/test_web_crm_routes.py -q` and verify expected route failures.
- [ ] Implement CRM payload models and protected routes.
- [ ] Add feedback target support for CRM entity ids where needed.
- [ ] Run `uv run --extra dev pytest tests/test_web_crm_routes.py -q` and verify it passes.
- [ ] Commit as `feat: add crm web api`.

### Task 5: Compact CRM UI

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [ ] Write failing page tests proving `/crm` is protected and exposes the CRM app shell.
- [ ] Run `uv run --extra dev pytest tests/test_web_pages.py -q` and verify the new assertions fail.
- [ ] Add `/crm` page with a client list, simple manual-client form, detail pane, contact reasons, and topbar link.
- [ ] Add a lead-detail conversion form for creating/linking a CRM client from a selected lead.
- [ ] Run `uv run --extra dev pytest tests/test_web_pages.py -q` and verify it passes.
- [ ] Commit as `feat: add compact crm workspace`.

### Task 6: Full Verification And Deploy

**Files:**
- Modify: plan checklist only after verification.

- [ ] Run `uv run --extra dev ruff check`.
- [ ] Run `uv run --extra dev ruff format --check`.
- [ ] Run `uv run --extra dev mypy src`.
- [ ] Run `uv run --extra dev pytest -q`.
- [ ] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [ ] Push `main`.
- [ ] SSH to `teamd-ams1`, pull fast-forward, rebuild web, run migrations, restart `web`, and verify `/health`.
