# Saved Queue Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browser-local saved filter presets for the candidate queue, including one optional default preset.

**Architecture:** Keep persistence in frontend `localStorage`. Add focused state utilities beside the existing queue state helpers, then wire those utilities into `CandidateQueueSection` and a small dialog component. Existing API query serialization remains authoritative for applying filters.

**Tech Stack:** React 19, TypeScript, MUI, MUI X DataGrid, Vitest, Testing Library.

---

### Task 1: Saved Filter State Utilities

**Files:**
- Modify: `frontend/src/analytics/candidateQueueState.ts`
- Test: `frontend/src/analytics/candidateQueueState.test.ts`

- [ ] **Step 1: Write failing tests**

Add tests for:
- loading empty/malformed saved filters returns `[]`;
- saving two presets preserves order and normalizes a single default;
- deleting a default leaves no custom default;
- default resolution applies a saved default only when no explicit queue query params exist.

Use localStorage key `pur-leads.analytics.saved-filters.v1`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd frontend
npm test -- --run src/analytics/candidateQueueState.test.ts
```

Expected: FAIL because saved-filter functions do not exist yet.

- [ ] **Step 3: Implement utilities**

Add:
- `CandidateQueueSavedFilter`;
- `loadCandidateSavedFilters()`;
- `saveCandidateSavedFilters(filters)`;
- `normalizeCandidateSavedFilters(value)`;
- `upsertCandidateSavedFilter(list, preset)`;
- `deleteCandidateSavedFilter(list, id)`;
- `candidateRouteHasExplicitFilters(params)`;
- `initialCandidateQueueStateFromSearchParams(params)`.

`initialCandidateQueueStateFromSearchParams` should return `{ filters, grid }`, using saved default only when `candidateRouteHasExplicitFilters(params)` is false.

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd frontend
npm test -- --run src/analytics/candidateQueueState.test.ts
```

Expected: PASS.

### Task 2: Route Initialization Uses Saved Default

**Files:**
- Modify: `frontend/src/analytics/analyticsRoutes.ts`
- Test: `frontend/src/analytics/candidateQueueState.test.ts`

- [ ] **Step 1: Write failing route/default test**

Add test that a URL with only `run` applies the local default preset, while a URL with `temperature=hot` ignores the local default.

- [ ] **Step 2: Implement route hook**

Change `parseAnalyticsUrlState` to call `initialCandidateQueueStateFromSearchParams(params)` instead of independently parsing filters/grid.

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd frontend
npm test -- --run src/analytics/candidateQueueState.test.ts
```

Expected: PASS.

### Task 3: Saved Filter Controls

**Files:**
- Create: `frontend/src/analytics/CandidateQueueSavedFilters.tsx`
- Modify: `frontend/src/analytics/CandidateQueueSection.tsx`

- [ ] **Step 1: Write failing UI tests**

Add focused `src/App.test.tsx` coverage or component-level coverage for:
- `Сохранить текущий` opens dialog;
- saved preset appears in selector/list;
- applying preset updates candidate API query;
- setting default persists in localStorage.

- [ ] **Step 2: Implement component**

Create `CandidateQueueSavedFilters` with:
- current saved filter selector;
- `Сохранить текущий`;
- management dialog;
- rename, update-from-current, set default, delete, apply actions.

Keep UI compact and reuse existing MUI controls.

- [ ] **Step 3: Wire into section**

In `CandidateQueueSection`:
- load saved filters into state;
- expose current queue state to the component;
- applying preset calls the same path as applying filters/grid state and resets offset to 0;
- saving/updating writes localStorage and component state.

- [ ] **Step 4: Run UI tests**

Run:

```bash
cd frontend
npm test -- --run src/App.test.tsx -t "analytics|queue|filter"
```

Expected: relevant tests PASS.

### Task 4: Verification

**Files:**
- No new files unless tests require minor updates.

- [ ] **Step 1: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 2: Run targeted queue tests**

Run:

```bash
cd frontend
npm test -- --run src/analytics/candidateQueueState.test.ts
npm test -- --run src/App.test.tsx -t "loads analytics dashboard|pages analytics candidates|selects analytics filters|filters analytics candidates"
```

Expected: PASS.

- [ ] **Step 3: Browser sanity**

Open `http://127.0.0.1:5173`, log in with dev credentials, and verify:
- saved-filter controls render;
- saving/applying a preset changes chips and query;
- no Vite overlay.
