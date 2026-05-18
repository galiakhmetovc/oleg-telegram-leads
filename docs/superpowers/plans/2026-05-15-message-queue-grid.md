# Message Queue Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework `Рабочее место -> Очередь` into a compact live message queue with rich message data, local column/filter controls, default 24h period, and a single row action modal.

**Architecture:** Extend the existing live analytics candidate API so each row includes message metadata plus latest LLM verification summary. Keep UI state local in `localStorage`, use the existing `AnalyticsPage`/MUI table structure, and avoid introducing a new grid dependency in this pass.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL JSONB, React 19, MUI, Vitest, pytest.

---

### Task 1: Backend Candidate Contract

**Files:**
- Modify: `backend/app/domain/analytics.py`
- Modify: `backend/app/api/analytics.py`
- Modify: `backend/app/infrastructure/persistence/analytics_repository.py`
- Test: `backend/tests/test_analytics_api.py`

- [ ] Write failing API tests that live candidates include `source_type`, `llm` summary, and support LLM filters.
- [ ] Add `AnalyticsCandidateLlmSummary` and optional `llm` field to the domain/API response.
- [ ] Add a latest-LLM subquery joined by `source_message_id`.
- [ ] Add query params for `source_type`, `llm_processed`, `llm_status`, `llm_verdict`, `llm_recommendation`, `llm_model`, `llm_route`, `llm_agrees_with_rules`, and `llm_has_error`.
- [ ] Run focused backend tests.

### Task 2: Frontend Message Types and Filters

**Files:**
- Modify: `frontend/src/analytics/types.ts`
- Modify: `frontend/src/AnalyticsPage.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] Write failing tests for default 24h queue, active filter chips, `Добавить фильтр`, and LLM filter query params.
- [ ] Extend `AnalyticsCandidate`/`CandidateFilters` with source and LLM fields.
- [ ] Replace always-visible filter row with chips and an add-filter modal.
- [ ] Persist active filters and quick period in `localStorage`.
- [ ] Run focused frontend tests.

### Task 3: Column Catalog and Local Layout

**Files:**
- Modify: `frontend/src/AnalyticsPage.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] Write failing tests for column picker, hiding/showing columns, source type column, and localStorage persistence.
- [ ] Add a column catalog covering message, enrichment, review, and LLM fields.
- [ ] Render table cells from visible column definitions.
- [ ] Add column picker with show/hide, up/down ordering, and width inputs.
- [ ] Persist column settings in `localStorage`.

### Task 4: Row Actions Modal

**Files:**
- Modify: `frontend/src/AnalyticsPage.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] Write failing tests that each row has only one `Действия` button and that modal actions route correctly.
- [ ] Replace inline action buttons and expand arrow with the action modal.
- [ ] Keep detailed analysis using existing `CandidateDetails`, triggered from the modal.
- [ ] Run focused frontend tests.

### Task 5: Verification

**Commands:**
- `cd backend && uv run pytest tests/test_analytics_api.py -q`
- `cd frontend && npm test -- --run src/App.test.tsx`
- `cd frontend && npm run build`

- [ ] Run all commands and record results.
