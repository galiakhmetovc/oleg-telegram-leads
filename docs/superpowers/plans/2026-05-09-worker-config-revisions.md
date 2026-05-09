# Worker Config Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make settings edits immediately affect new worker jobs without manual worker restarts, while making stale Python worker code visible in runtime status.

**Architecture:** Persist the NLP config revision claimed by each enrichment job, cache compiled pipelines by revision inside the worker, and expose backend/worker runtime versions plus latest worker config revision in system status. In dev, wrap the Celery worker with `watchfiles` so Python code edits restart the worker process.

**Tech Stack:** FastAPI, Celery, SQLAlchemy/Alembic, PostgreSQL JSONB, React runtime status page, Docker Compose dev services.

---

### Task 1: Persist Claimed NLP Config Revision

**Files:**
- Create: `backend/alembic/versions/0030_enrichment_config_revision.py`
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Modify: `backend/app/domain/enrichment.py`
- Modify: `backend/app/infrastructure/persistence/enrichment_repository.py`
- Modify: `backend/app/api/enrichments.py`
- Test: `backend/tests/test_enrichment_api.py`

- [x] Add nullable `nlp_config_revision_id` and `nlp_config_revision` columns to `enrichment_jobs`.
- [x] Extend `EnrichmentJobSnapshot` and API serialization with those fields.
- [x] Change `claim_queued_job` to accept and persist revision id/number atomically with the status transition.
- [x] Add/update tests that assert serialized job snapshots include the revision fields.

### Task 2: Worker Uses Active Revision At Claim And Caches Pipelines

**Files:**
- Modify: `backend/app/worker/tasks.py`
- Test: `backend/tests/test_worker_notifications.py`

- [x] Add a small `CompiledPipeline` helper in `tasks.py` keyed by active config revision id.
- [x] Resolve active config revision before claiming the queued job.
- [x] Pass revision id/number into `claim_queued_job`.
- [x] Reuse cached `RussianTextEnricher` and stage metadata for the same revision.
- [x] Add tests proving non-queued redelivery still exits early and queued jobs claim a revision.

### Task 3: Runtime Status Shows Config/Code Freshness

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/infrastructure/persistence/runtime_repository.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `docker-compose.yml`
- Test: `backend/tests/test_runtime_api.py`

- [x] Add `PUR_CODE_VERSION` and `PUR_PROCESS_ROLE` settings with dev defaults.
- [x] Add worker `code_version` and `nlp_config_revision` into worker job events.
- [x] Add active NLP config revision and latest worker job revision/version to system status.
- [x] Mark worker status warning if latest worker code version is known and differs from backend code version.
- [x] Add API tests for the extra status details.

### Task 4: Dev Worker Autorestart And Documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `state/current.md`
- Modify: `docs/architecture.md`

- [x] Wrap worker command in `watchfiles --filter python`.
- [x] Set `PUR_PROCESS_ROLE` for backend and worker services.
- [x] Document that settings changes do not require restart, while code changes are handled by dev autorestart/stale status.
- [x] Run `docker compose config --quiet`.

### Task 5: Verification

**Files:**
- No new files.

- [x] Run `cd backend && uv run ruff check .`.
- [x] Run `cd backend && uv run mypy .`.
- [x] Run `cd backend && uv run pytest -q`.
- [x] Run `docker compose run --rm migrate`.
- [x] Run a runtime smoke: create a Testing/Golden job after migration and verify the job exposes `nlp_config_revision`.
- [ ] Commit the completed implementation.
