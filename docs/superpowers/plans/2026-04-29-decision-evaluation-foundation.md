# Decision Evaluation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make lead/catalog/CRM decisions traceable and add the first quality evaluation foundation so system behavior can be measured instead of guessed.

**Architecture:** Add a shared `decision_records` table for explainable system outputs, plus evaluation datasets/cases/runs/results and aggregate quality snapshots. Keep the first pass deterministic and local: no new AI provider behavior, no vector search, no full Research workflow. Wire lead detection and feedback promotion into this layer, then expose it through authenticated operations/quality APIs.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy Core tables, Alembic migrations, SQLite, pytest, ruff, mypy.

---

### Task 1: Schema And Models

**Files:**
- Create: `migrations/versions/0011_decision_evaluation_foundation.py`
- Create: `src/pur_leads/models/evaluation.py`
- Modify: `tests/test_db_migrations.py`
- Test: `tests/test_evaluation_migration.py`

- [ ] **Step 1: Write failing migration tests**

Assert that `decision_records`, `evaluation_datasets`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`, and `quality_metric_snapshots` exist after `upgrade_database()`, and that key columns exist.

- [ ] **Step 2: Run migration tests to verify RED**

Run: `pytest tests/test_db_migrations.py tests/test_evaluation_migration.py -q`

Expected: fail because the tables do not exist yet.

- [ ] **Step 3: Add Alembic migration and table definitions**

Create the migration after `0010_backup_restore_foundation`. Keep constraints broad but explicit for statuses and core enum-like fields.

- [ ] **Step 4: Run migration tests to verify GREEN**

Run: `pytest tests/test_db_migrations.py tests/test_evaluation_migration.py -q`

Expected: pass.

### Task 2: Repository And Service

**Files:**
- Create: `src/pur_leads/repositories/evaluation.py`
- Create: `src/pur_leads/services/evaluation.py`
- Test: `tests/test_evaluation_service.py`

- [ ] **Step 1: Write failing service tests**

Cover:
- recording a decision with input/evidence/version metadata;
- creating/finding the default feedback regression dataset;
- promoting a feedback event into an evaluation case idempotently;
- completing an evaluation run with per-case results and metrics.

- [ ] **Step 2: Run service tests to verify RED**

Run: `pytest tests/test_evaluation_service.py -q`

Expected: fail because repository/service do not exist.

- [ ] **Step 3: Implement minimal repository/service**

Use existing repository style with dataclass records and SQLAlchemy Core. The service should commit at operation boundaries, like existing lead/catalog services.

- [ ] **Step 4: Run service tests to verify GREEN**

Run: `pytest tests/test_evaluation_service.py -q`

Expected: pass.

### Task 3: Lead Decision Trace Integration

**Files:**
- Modify: `src/pur_leads/services/leads.py`
- Test: `tests/test_lead_event_service.py`

- [ ] **Step 1: Write failing integration test**

When `LeadService.record_detection()` creates a new lead event, assert that a `decision_records` row is created with `decision_type = lead_detection`, `entity_type = lead_event`, `entity_id = lead_event.id`, classifier version, source message, confidence, reason, and evidence summary.

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/test_lead_event_service.py::test_record_detection_creates_decision_trace -q`

Expected: fail because no trace exists.

- [ ] **Step 3: Wire decision recording**

Call `EvaluationService.record_decision()` after the lead event and match rows are created, before the transaction commits.

- [ ] **Step 4: Run lead tests to verify GREEN**

Run: `pytest tests/test_lead_event_service.py tests/test_evaluation_service.py -q`

Expected: pass.

### Task 4: Feedback Regression Promotion

**Files:**
- Modify: `src/pur_leads/services/leads.py`
- Test: `tests/test_lead_feedback_service.py`

- [ ] **Step 1: Write failing feedback test**

When meaningful lead feedback is recorded with `application_status = recorded`, assert that a feedback regression evaluation case can be created and links back to the feedback event in `context_json`.

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/test_lead_feedback_service.py::test_feedback_can_promote_regression_case -q`

Expected: fail because no promotion service is wired.

- [ ] **Step 3: Implement promotion helper**

Add explicit service method and call it only for actions that represent a classifier-quality signal. Commercial work outcomes stay outside classifier learning by default.

- [ ] **Step 4: Run feedback tests to verify GREEN**

Run: `pytest tests/test_lead_feedback_service.py tests/test_evaluation_service.py -q`

Expected: pass.

### Task 5: Quality APIs And Operations Summary

**Files:**
- Create: `src/pur_leads/web/routes_quality.py`
- Modify: `src/pur_leads/web/app.py`
- Modify: `src/pur_leads/web/routes_operations.py`
- Modify: `src/pur_leads/web/static/app.js`
- Test: `tests/test_web_quality_routes.py`
- Test: `tests/test_web_operations_routes.py`

- [ ] **Step 1: Write failing route tests**

Authenticated admin can list quality summary, datasets, cases, runs, and failed results. Operations summary includes quality counts and recent failed evaluation runs.

- [ ] **Step 2: Run route tests to verify RED**

Run: `pytest tests/test_web_quality_routes.py tests/test_web_operations_routes.py -q`

Expected: fail because routes are missing.

- [ ] **Step 3: Implement routes and minimal UI hooks**

Expose `/api/quality/summary`, `/api/quality/datasets`, `/api/quality/cases`, `/api/quality/runs`, and `/api/quality/results`. Add a lightweight Quality section to the existing frontend router, reusing the Operations table patterns.

- [ ] **Step 4: Run route tests to verify GREEN**

Run: `pytest tests/test_web_quality_routes.py tests/test_web_operations_routes.py -q`

Expected: pass.

### Task 6: Verification And Commit

**Files:**
- All changed files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_evaluation_migration.py tests/test_evaluation_service.py tests/test_lead_event_service.py tests/test_lead_feedback_service.py tests/test_web_quality_routes.py tests/test_web_operations_routes.py -q`

- [ ] **Step 2: Run full verification**

Run:
- `ruff check`
- `ruff format --check`
- `mypy src`
- `node --check src/pur_leads/web/static/app.js`
- `pytest -q`

- [ ] **Step 3: Commit and push**

Commit message: `feat: add decision evaluation foundation`

