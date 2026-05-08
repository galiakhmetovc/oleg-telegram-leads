# Review Constructor Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build active Review-page constructor flows for dictionaries, facts, and domain signals.

**Architecture:** Keep PostgreSQL NLP revisions as the source of truth. FastAPI routes stay thin and call application settings use cases that mutate config documents, validate them, and persist a new revision through the existing repository port.

**Tech Stack:** FastAPI, Pydantic, PostgreSQL-backed settings repository, React/Vite/TypeScript, MUI, Vitest, pytest.

---

### Task 1: Backend Constructor API

**Files:**
- Modify: `backend/app/application/settings/use_cases.py`
- Modify: `backend/app/api/settings.py`
- Test: `backend/tests/test_settings_api.py`

- [ ] Write failing API tests for `/constructor/alias`, `/constructor/fact`, and `/constructor/signal`.
- [ ] Implement reusable document mutation helpers for alias catalogs and rule collections.
- [ ] Add Pydantic request/response models and FastAPI endpoints.
- [ ] Run `uv run pytest tests/test_settings_api.py -q`.

### Task 2: Review UI Dialogs

**Files:**
- Modify: `frontend/src/AnalyticsPage.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] Write failing UI test for alias/fact/signal constructor actions.
- [ ] Add compact constructor dialog state and MUI dialogs.
- [ ] Submit constructor payloads to backend and refresh settings cache from response.
- [ ] Run `npm test -- --run App.test.tsx -t constructor`.

### Task 3: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`
- Modify: `state/current.md`
- Modify: `state/backlog.md`

- [ ] Update docs to describe active constructor flows.
- [ ] Run backend pytest/ruff/mypy, frontend tests/build, `docker compose config`, and `git diff --check`.
- [ ] Commit the completed slice.
