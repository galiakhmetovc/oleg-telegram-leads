# Worker Config Revisions And Stale Code Detection

## Problem

PUR Leads has two different kinds of runtime changes:

- product/NLP settings changed by the operator in PostgreSQL;
- backend Python code changed by a developer.

The first kind must not require restarting the worker. The second kind cannot be
made safe by PostgreSQL revisions alone: a running Celery process has already
imported Python modules and may continue to execute old scoring code.

The current failure mode is confusing: Backend/API may use fresh code while the
worker still uses old code, so Testing/Golden/Celery results can disagree with
direct backend checks.

## Goals

- Workers keep accepting messages after settings changes.
- Every enrichment result records the exact NLP config revision it used.
- New jobs use the latest active config revision unless explicitly pinned.
- Already-running jobs are not interrupted by settings changes.
- Operators can see when worker code is stale compared with the backend code.
- Development mode reloads or restarts worker code automatically where practical.

## Non-Goals

- No production rolling-deploy mechanism in this slice.
- No automatic bulk reprocessing of old Telegram messages after every settings
  change.
- No attempt to hot-reload imported Python modules inside a live Celery worker.

## Runtime Model

### Settings Changes

Settings are saved as immutable `nlp_config_revisions` rows. The active row is
the source of truth.

For a new enrichment job, the worker resolves the active config revision when it
claims the job. The worker then builds or reuses a compiled NLP pipeline for that
revision and processes the text.

If settings change while a job is already running, that job finishes with the
revision it already claimed. Later jobs use the newer active revision.

### Result Traceability

`enrichment_jobs` should store the claimed NLP config revision id/number before
processing starts. `enrichment_results` should also expose the used revision in
the serialized result payload or through the joined job metadata.

The UI should show this revision in Testing, Golden, Analytics, and Review
evidence so an operator can answer: "Which rules produced this result?"

### Worker Config Cache

Workers may cache compiled `RussianTextEnricher` instances by config revision.
The cache key is the active revision id or revision number. A cache hit avoids
rebuilding Yargy parsers and alias matchers for every job. A cache miss compiles
the pipeline from the revision documents.

The cache must be bounded, for example keep only the latest few revisions, so a
long-running worker cannot grow memory indefinitely after many settings edits.

### Code Changes

Python code changes are different from settings changes. A running Celery worker
cannot safely observe changes to imported modules.

In development, worker code should restart automatically when backend `.py`
files change. If automatic restart is not active, System Status must show a
clear stale-code warning.

In production, code changes are handled by deployment/rolling restart. That is a
separate operational design.

## Queue Semantics

Queued jobs that have not yet been claimed should use the latest active config
revision at claim time.

Rationale: Telegram live processing should reflect the rules that are current
when the system actually analyzes the message. If an operator wants a historical
comparison, they should use explicit reprocessing or Golden runs.

Pinned revision processing can be added later for eval/reproducibility, but the
default live path stays "latest active at claim".

## UI And Status

System Status should show:

- active NLP config revision;
- latest completed worker job config revision;
- backend code version;
- worker code version;
- a warning if backend and worker code versions differ;
- worker queue counts by pending/running/failed/completed where already
  available.

Settings and Review Constructor save flows should not ask the operator to
restart the worker. After saving settings, the UI can show: "New messages will
use revision N; existing results are unchanged until reprocessed."

Testing/Golden result pages should show the used revision near score/evidence.

## Reprocessing

Changing settings does not mutate existing enrichment results. Existing
Analytics rows remain auditable evidence produced by their recorded revision.

Reprocessing is explicit:

- single message: from Review/Analytics/Testing;
- Golden example: run button;
- batch/recent messages: later operator action with limits and progress.

Reprocessing creates a new enrichment job and stores a new result tied to the
same source message only when the operator chooses to replace/update the live
analysis.

## Error Handling

Saving settings validates the full config before activation. Invalid revisions
are rejected and never become active.

If a worker cannot compile the active revision, the job fails with an explicit
error payload containing the revision id/number. System Status should surface
recent config-compilation failures.

If worker code is stale, jobs may still run, but the UI must mark the runtime as
stale so the operator understands that results can disagree with backend checks.

## Testing

Backend tests should cover:

- worker claims and records the active config revision;
- a job queued before a settings change uses the newer revision if claimed after
  the change;
- a running job remains tied to the revision it claimed;
- compiled pipeline cache invalidates on revision change;
- stale backend/worker code versions are reflected in runtime status.

Integration smoke should cover:

- save NLP settings;
- run Testing or Golden without restarting worker;
- verify the new job used the new revision and produced expected evidence.
