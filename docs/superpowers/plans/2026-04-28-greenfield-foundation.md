# PUR Leads Greenfield Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy Telegram-leads prototype with a clean foundation for the full PUR catalog, lead detection, CRM, archive, and web system described in the source-of-truth spec.

**Architecture:** Build a new Python monolith with clear internal modules, SQLite as the operational database, Alembic migrations, typed settings, audit/operational logs, secret references, and a resumable scheduler. The existing code is treated as legacy reference only and must not be used as the runtime base.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, SQLite FTS5, pytest, pytest-asyncio, Ruff, MyPy, Telethon in later plans.

---

## Scope

This plan is only the greenfield foundation. It deliberately does not implement Telegram ingestion, PUR catalog parsing, AI classification, CRM screens, or archive rotation yet. Those are separate follow-up implementation plans built on this foundation.

The current application code is legacy. Do not refactor it. The first implementation task removes tracked legacy runtime files so future work cannot accidentally extend the wrong architecture.

Keep:

- `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`
- this plan and future plans under `docs/superpowers/plans/`
- local untracked runtime secrets/sessions, but never commit them

Remove or replace:

- old `src/` package
- old Telegram command scripts
- old JSON/checkpoint tests
- old README/config docs that describe the legacy behavior
- old Docker files if they encode legacy entrypoints

## File Structure

Create this structure:

```text
pyproject.toml
README.md
docker-compose.yml
Dockerfile
.env.example
src/pur_leads/
  __init__.py
  app.py
  cli.py
  core/
    __init__.py
    config.py
    time.py
    ids.py
  db/
    __init__.py
    engine.py
    migrations.py
    session.py
  models/
    __init__.py
    audit.py
    settings.py
    secrets.py
    scheduler.py
  repositories/
    __init__.py
    audit.py
    settings.py
    secrets.py
    scheduler.py
  services/
    __init__.py
    audit.py
    settings.py
    secrets.py
    scheduler.py
  web/
    __init__.py
    app.py
    routes_health.py
alembic.ini
migrations/
  env.py
  script.py.mako
  versions/
tests/
  conftest.py
  test_app_health.py
  test_db_migrations.py
  test_settings_service.py
  test_audit_log.py
  test_secret_refs.py
  test_scheduler_jobs.py
```

Responsibilities:

- `core/config.py`: environment parsing, paths, app settings.
- `db/engine.py`: SQLite engine creation, pragmas, WAL, foreign keys.
- `db/migrations.py`: programmatic migration helpers for CLI/tests.
- `models/*`: SQLAlchemy tables for foundation objects only.
- `repositories/*`: thin persistence operations, no business policy.
- `services/*`: typed behavior, validation, audit writes, scheduler leases.
- `web/*`: FastAPI app factory and health route only.
- `cli.py`: `pur-leads` command group for migration, settings, and worker smoke commands.

## Task 1: Controlled Legacy Purge

**Files:**
- Delete: `src/__init__.py`
- Delete: `src/ai_analyzer.py`
- Delete: `src/config.py`
- Delete: `src/fetcher.py`
- Delete: `src/keyword_scanner.py`
- Delete: `src/notifier.py`
- Delete: `src/pipeline.py`
- Delete: `tests/__init__.py`
- Delete: `tests/get_message.py`
- Delete: `tests/test_ai_analyzer.py`
- Delete: `tests/test_caption_and_prompt.py`
- Delete: `tests/test_fetcher_pending.py`
- Delete: `tests/test_handle_link.py`
- Delete: `tests/test_it_rejection.py`
- Delete: `tests/test_msg_716254.py`
- Delete: `tests/test_pipeline_checkpoint.py`
- Delete: `tests/test_recheck.py`
- Delete: `test_ai_direct.py`
- Delete: `test_ai_real.py`
- Delete: `tg-auth.py`
- Delete: `tg-connect.py`
- Delete: `config.example.py`
- Delete: `reset_and_rebuild.sh`
- Delete: `docs/architecture.md`
- Delete: `docs/config.md`
- Delete: `docs/decisions.md`
- Delete: `docs/keywords.md`
- Delete: `docs/prompts.md`
- Replace: `README.md`
- Replace: `requirements.txt` with `pyproject.toml`
- Replace: `Dockerfile`
- Replace: `docker-compose.yml`
- Keep local only: `.env`, `*.session`, `sessions/`, `data/`, `artifacts/`

- [x] **Step 1: Confirm dirty state before deletion**

Run:

```bash
git status --short
```

Expected: legacy files may be dirty. Confirm the product owner has explicitly approved deleting legacy code despite those local changes.

- [x] **Step 2: Delete tracked legacy files**

Use `apply_patch` delete hunks or `git rm` for tracked files only. Do not delete untracked `.env`, session files, runtime `data/`, or `artifacts/`.

- [x] **Step 3: Create placeholder greenfield README**

Create `README.md`:

```markdown
# PUR Leads

Greenfield implementation for PUR catalog source-of-truth, Telegram lead detection, and lightweight CRM.

The current source of truth is `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`.
```

- [x] **Step 4: Verify no legacy Python package remains**

Run:

```bash
rg -n "Pipeline|KeywordScanner|AIAnalyzer|chats.json|leads.json|/run|/recheck" .
```

Expected: no matches outside deleted legacy diffs or the historical spec, if the spec mentions migration context.

- [x] **Step 5: Commit purge**

Run:

```bash
git add -A
git commit -m "chore: remove legacy prototype"
```

Expected: one commit removing old runtime files and replacing README only.

## Task 2: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/pur_leads/__init__.py`
- Create: `src/pur_leads/app.py`
- Create: `src/pur_leads/cli.py`
- Create: `src/pur_leads/core/config.py`
- Create: `src/pur_leads/core/time.py`
- Create: `src/pur_leads/core/ids.py`
- Create: `tests/conftest.py`
- Create: `tests/test_app_health.py`

- [x] **Step 1: Write failing health test**

```python
from fastapi.testclient import TestClient

from pur_leads.web.app import create_app


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [x] **Step 2: Add dependencies and tooling**

Create `pyproject.toml` with:

```toml
[project]
name = "pur-leads"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13",
  "fastapi>=0.115",
  "httpx>=0.28",
  "pydantic-settings>=2.7",
  "sqlalchemy>=2.0",
  "uvicorn>=0.34",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.14",
  "pytest>=8.3",
  "pytest-asyncio>=0.25",
  "ruff>=0.9",
]

[project.scripts]
pur-leads = "pur_leads.cli:main"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
```

- [x] **Step 3: Implement app factory and health route**

Create `src/pur_leads/web/app.py` and `src/pur_leads/web/routes_health.py` with a minimal FastAPI app and `/health` route.

- [x] **Step 4: Run test**

Run:

```bash
python -m pytest tests/test_app_health.py -q
```

Expected: pass.

- [x] **Step 5: Run formatting and linting**

Run:

```bash
python -m ruff format .
python -m ruff check .
```

Expected: pass.

- [x] **Step 6: Commit scaffold**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffold greenfield app"
```

## Task 3: SQLite Engine And Migration Baseline

**Files:**
- Create: `src/pur_leads/db/engine.py`
- Create: `src/pur_leads/db/session.py`
- Create: `src/pur_leads/db/migrations.py`
- Create: `src/pur_leads/models/__init__.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_foundation.py`
- Test: `tests/test_db_migrations.py`

- [x] **Step 1: Write migration test**

```python
from sqlalchemy import inspect

from pur_leads.db.engine import create_sqlite_engine
from pur_leads.db.migrations import upgrade_database


def test_foundation_migration_creates_core_tables(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_sqlite_engine(db_path)

    upgrade_database(engine)

    tables = set(inspect(engine).get_table_names())
    assert {"settings", "settings_revisions", "audit_log", "operational_events"}.issubset(tables)
```

- [x] **Step 2: Implement SQLite engine pragmas**

`create_sqlite_engine()` must enable:

- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL`
- `PRAGMA busy_timeout = 5000`

- [x] **Step 3: Add Alembic baseline migration**

Migration `0001_foundation.py` creates these first tables:

- `settings`
- `settings_revisions`
- `secret_refs`
- `audit_log`
- `operational_events`
- `scheduler_jobs`
- `job_runs`

Keep only foundation columns from the spec. Do not add Telegram/catalog/CRM tables in this task.

- [x] **Step 4: Run migration test**

```bash
python -m pytest tests/test_db_migrations.py -q
```

Expected: pass.

- [x] **Step 5: Commit database baseline**

```bash
git add alembic.ini migrations src/pur_leads/db src/pur_leads/models tests/test_db_migrations.py
git commit -m "feat: add sqlite migration baseline"
```

## Task 4: Typed Settings Service

**Files:**
- Create: `src/pur_leads/models/settings.py`
- Create: `src/pur_leads/repositories/settings.py`
- Create: `src/pur_leads/services/settings.py`
- Test: `tests/test_settings_service.py`

- [x] **Step 1: Write failing tests**

Cover:

- inserting a new setting stores `value_json`, `value_type`, `scope`, and `updated_by`;
- updating a setting creates `settings_revisions`;
- getting an unknown setting returns the defined default;
- secret settings can only store a secret reference id, not a raw value.

- [x] **Step 2: Implement repository**

Repository methods:

- `get(key, scope="global", scope_id=None)`
- `set(key, value, value_type, updated_by, scope="global", scope_id=None, reason=None)`
- `list(scope=None)`

- [x] **Step 3: Implement service defaults**

Add a typed default registry containing at least:

- `telegram_worker_count = 1`
- `telegram_read_jobs_per_userbot = 1`
- `catalog_ingestion_pur_channel_enabled = true`
- `lead_monitoring_public_groups_enabled = true`
- `backup_sessions_enabled = false`
- `backup_secret_values_enabled = false`
- `backup_encryption_required_for_secrets = true`

- [x] **Step 4: Run tests**

```bash
python -m pytest tests/test_settings_service.py -q
```

Expected: pass.

- [x] **Step 5: Commit settings service**

```bash
git add src/pur_leads/models/settings.py src/pur_leads/repositories/settings.py src/pur_leads/services/settings.py tests/test_settings_service.py
git commit -m "feat: add typed settings service"
```

## Task 5: Audit, Operational Events, And Secret References

**Files:**
- Create: `src/pur_leads/models/audit.py`
- Create: `src/pur_leads/models/secrets.py`
- Create: `src/pur_leads/repositories/audit.py`
- Create: `src/pur_leads/repositories/secrets.py`
- Create: `src/pur_leads/services/audit.py`
- Create: `src/pur_leads/services/secrets.py`
- Test: `tests/test_audit_log.py`
- Test: `tests/test_secret_refs.py`

- [x] **Step 1: Write audit tests**

Verify:

- audit entries store actor, action, entity type/id, old/new JSON;
- operational events store severity, correlation id, and details JSON;
- secret values never appear in audit or operational event payloads.

- [x] **Step 2: Write secret reference tests**

Verify:

- creating `telegram_session`, `telegram_api`, `ai_api_key`, and `web_session_secret` refs;
- UI-safe DTO exposes display name/status/storage backend but not value;
- missing secret checks create masked operational events.

- [x] **Step 3: Implement services**

Keep services narrow:

- `AuditService.record_change(...)`
- `AuditService.record_event(...)`
- `SecretRefService.create_ref(...)`
- `SecretRefService.mark_missing(...)`
- `SecretRefService.public_view(...)`

- [x] **Step 4: Run tests**

```bash
python -m pytest tests/test_audit_log.py tests/test_secret_refs.py -q
```

Expected: pass.

- [x] **Step 5: Commit audit and secrets**

```bash
git add src/pur_leads/models src/pur_leads/repositories src/pur_leads/services tests/test_audit_log.py tests/test_secret_refs.py
git commit -m "feat: add audit and secret references"
```

## Task 6: Scheduler Job Foundation

**Files:**
- Create: `src/pur_leads/models/scheduler.py`
- Create: `src/pur_leads/repositories/scheduler.py`
- Create: `src/pur_leads/services/scheduler.py`
- Test: `tests/test_scheduler_jobs.py`

- [x] **Step 1: Write scheduler tests**

Cover:

- enqueue job with `job_type`, `scope_type`, `scope_id`, `idempotency_key`;
- duplicate idempotency key returns the existing queued/running job;
- acquiring a job sets `locked_by`, `locked_at`, and `lease_expires_at`;
- expired lease can be recovered by another worker;
- failed job increments attempt count and schedules `next_retry_at`;
- Telegram jobs are serialized per `userbot_account_id`.

- [x] **Step 2: Implement repository queries**

Repository methods:

- `enqueue(...)`
- `acquire_next(worker_name, now)`
- `succeed(job_id, checkpoint_after, result_summary)`
- `fail(job_id, error, retry_at)`
- `recover_expired_leases(now)`

- [x] **Step 3: Implement service policy**

Use SQL-visible fields from the spec. Do not hide source/account scope only in `payload_json`.

- [x] **Step 4: Run tests**

```bash
python -m pytest tests/test_scheduler_jobs.py -q
```

Expected: pass.

- [x] **Step 5: Commit scheduler foundation**

```bash
git add src/pur_leads/models/scheduler.py src/pur_leads/repositories/scheduler.py src/pur_leads/services/scheduler.py tests/test_scheduler_jobs.py
git commit -m "feat: add scheduler job foundation"
```

## Task 7: CLI, Docker, And Developer Workflow

**Files:**
- Modify: `src/pur_leads/cli.py`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`

- [x] **Step 1: Add CLI commands**

Commands:

- `pur-leads db upgrade`
- `pur-leads settings list`
- `pur-leads settings set KEY JSON_VALUE`
- `pur-leads worker once`
- `pur-leads web`

- [x] **Step 2: Add Docker entrypoints**

Compose services:

- `web`: FastAPI app
- `worker`: scheduler worker placeholder

Use local volumes:

- `./data:/app/data`
- `./artifacts:/app/artifacts`
- `./sessions:/app/sessions`

- [x] **Step 3: Update `.env.example`**

Include only non-secret examples and secret ref paths:

- `PUR_DATABASE_PATH=/app/data/pur-leads.sqlite3`
- `PUR_LOG_LEVEL=INFO`
- `PUR_WEB_HOST=0.0.0.0`
- `PUR_WEB_PORT=8000`

- [x] **Step 4: Verify commands**

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src
```

Expected: pass.

- [x] **Step 5: Commit workflow**

```bash
git add Dockerfile docker-compose.yml .env.example README.md src/pur_leads/cli.py
git commit -m "chore: add greenfield developer workflow"
```

## Task 8: Foundation Acceptance Gate

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/plans/2026-04-28-telegram-source-ingestion.md`

- [ ] **Step 1: Run full foundation verification**

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src
docker compose config
```

Expected: all pass.

- [ ] **Step 2: Verify no legacy runtime references remain**

```bash
rg -n "chats.json|leads.json|KeywordScanner|AIAnalyzer|Pipeline|/recheck|/leads" README.md src tests Dockerfile docker-compose.yml
```

Expected: no matches.

- [ ] **Step 3: Commit acceptance docs**

```bash
git add README.md docs/superpowers/plans/2026-04-28-telegram-source-ingestion.md
git commit -m "docs: prepare telegram ingestion plan"
```

## Follow-Up Plans

Create and execute these plans after the foundation passes:

1. `2026-04-28-telegram-source-ingestion.md`: userbot accounts, monitored sources, source access checks, source messages, checkpoints, polling worker.
2. `2026-04-28-pur-catalog-ingestion.md`: PUR channel sync, document download policy, Telegraph/external fetch, artifacts, parsed chunks, catalog extraction runs.
3. `2026-04-28-catalog-review-and-classifier.md`: catalog candidates, operational catalog, classifier versions, snapshot entries, examples, lead detection output.
4. `2026-04-28-leads-inbox-and-notifications.md`: lead events, matches, clusters, feedback, notification policy, Telegram urgent signal channel.
5. `2026-04-28-crm-contact-reasons.md`: clients, contacts, interests, assets, support, opportunities, contact reasons.
6. `2026-04-28-web-admin-ui.md`: bootstrap admin, Telegram auth, settings UI, Sources, Catalog Review, Leads Inbox, CRM screens.
7. `2026-04-28-quality-archive-backup.md`: evaluation datasets/runs, archive segments, restore jobs, local backups, secret hygiene.

Each follow-up plan must start from the same source-of-truth spec and must not reintroduce a second runtime path.
