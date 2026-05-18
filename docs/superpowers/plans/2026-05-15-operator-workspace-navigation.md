# Operator Workspace Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the operator UI so queue, review, testing, and constructor live under `Рабочее место`, while reports stay under `Аналитика`.

**Architecture:** Keep existing page components and backend APIs. Add a small workspace sub-navigation in `App.tsx`, route top-level tabs to operator/reporting modes, and let `AnalyticsPage` hide candidate tabs in report mode or report tabs in workspace mode.

**Tech Stack:** React, Vite, MUI Tabs, Vitest + Testing Library.

---

### Task 1: Navigation Contract

**Files:**
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] Add failing test that top nav has `Рабочее место`, not separate top-level `Тестирование`/`Конструктор`.
- [ ] Add failing test that `/testing` selects `Рабочее место` and inner `Проверка`.
- [ ] Implement workspace sub-tabs and top-level route selection.

### Task 2: Analytics Split

**Files:**
- Modify: `frontend/src/AnalyticsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] Add failing test that `/analytics/overview` selects top-level `Аналитика`.
- [ ] Add `sectionScope` to `AnalyticsPage`.
- [ ] In workspace scope, render only candidate queue.
- [ ] In reports scope, render overview/quality/LLM tabs and default to overview.

### Task 3: Verification

**Files:**
- Run focused frontend tests and lint/type checks available in the project.

- [ ] Run `npm test -- --run src/App.test.tsx`.
- [ ] Run project frontend verification command if available.
