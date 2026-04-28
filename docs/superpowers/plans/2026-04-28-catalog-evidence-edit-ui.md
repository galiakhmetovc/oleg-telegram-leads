# Catalog Evidence And Edit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make catalog candidate review practical by showing source evidence and allowing an administrator to correct extracted candidate fields before approval.

**Architecture:** Extend the existing authenticated catalog review API. Keep candidate listing lightweight; load full candidate detail on selection with evidence, source, chunk, and artifact context. Save human corrections through an audited PATCH endpoint before the existing approve/reject flow.

**Tech Stack:** FastAPI, SQLAlchemy Core, existing admin cookie auth, vanilla JS/CSS, pytest.

---

## Task 1: Detail And Evidence API

**Files:**
- Modify: `src/pur_leads/repositories/catalog_candidates.py`
- Modify: `src/pur_leads/services/catalog_candidates.py`
- Modify: `src/pur_leads/web/routes_catalog.py`
- Test: `tests/test_web_catalog_routes.py`

- [x] Add candidate detail endpoint.
- [x] Return direct candidate evidence with source, parsed chunk, and artifact context.
- [x] Keep list endpoint compact.
- [x] Cover unauthorized access and evidence payload shape.

## Task 2: Candidate Edit API

**Files:**
- Modify: `src/pur_leads/services/catalog_candidates.py`
- Modify: `src/pur_leads/web/routes_catalog.py`
- Test: `tests/test_web_catalog_routes.py`

- [x] Add audited PATCH endpoint for `canonical_name` and `normalized_value`.
- [x] Validate empty canonical names.
- [x] Verify approval promotes the edited candidate data.

## Task 3: Catalog Review UI

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [x] Load candidate detail after queue selection.
- [x] Render editable name and JSON payload.
- [x] Render source/chunk evidence.
- [x] Save edits before review actions.

## Task 4: Verification And Rollout

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `node --check src/pur_leads/web/static/app.js`.
- [x] Run `TMPDIR=/home/admin/AI-AGENT/data/tmp/oleg-telegram-leads-pytest uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out` and report only line count.
- [ ] Commit and push to `main`.
- [ ] Deploy on `teamd-ams1`, restart web/worker, and verify `/health` plus `docker compose ps web worker`.
