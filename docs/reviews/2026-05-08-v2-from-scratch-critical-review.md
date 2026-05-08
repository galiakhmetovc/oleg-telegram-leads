# Critical Review: v2-from-scratch

Date: 2026-05-08

Reviewed worktree:
`/home/admin/.config/superpowers/worktrees/oleg-telegram-leads/v2-from-scratch`

## Verdict

This is a strong development slice: the architecture is intentional, the test
base is already useful, and backend/frontend/compose checks pass. It is not yet
a robust product contour. The main risks are in the batch analytics contract,
background job reliability, concurrent settings revisions, and analytics filter
performance.

## Findings

1. Background job creation is not atomic with Celery publication.

   `backend/app/application/enrichment/use_cases.py:24` creates the database
   job, then `backend/app/application/enrichment/use_cases.py:25` publishes to
   Celery as a separate operation. If publishing fails after the database commit,
   the job stays `queued` forever. This needs an outbox/retry model or an
   explicit fail state when publish fails.

2. Worker redelivery can re-run a completed job.

   `backend/app/worker/tasks.py:26` reads the snapshot and
   `backend/app/worker/tasks.py:39` immediately marks it running. There is no
   status guard for already completed or failed jobs. A Celery redelivery after a
   worker crash or ack race can re-run a completed job and append duplicate
   events.

3. The tracked code cannot reproduce the documented batch analytics pipeline.

   `backend/app/cli/batch_enrich.py:91` writes full enrichment rows with the
   payload under `result`. `backend/app/cli/import_analytics.py:68` expects a
   compact row where `lead_assessment`, `domain_signals`, and `facts` are at the
   top level. README documents `lead-candidates.jsonl`, but the generator for
   that compact file is not present in tracked code.

4. Analytics filter indexes do not match the query shape.

   `backend/app/infrastructure/persistence/analytics_repository.py:68` and
   related filters use `value = ANY(array_col)`. The migrations create GIN
   indexes on array columns in
   `backend/alembic/versions/0003_analytics.py:74` and
   `backend/alembic/versions/0004_analytics_filter_indexes.py:18`. That query
   shape needs to be checked with `EXPLAIN ANALYZE`; it is not the usual shape
   that benefits from array GIN indexes. Text search also uses `ILIKE '%q%'` in
   `backend/app/infrastructure/persistence/analytics_repository.py:78`, which
   needs trigram/full-text indexing or a different search path before larger
   imports.

5. Settings preview blocks the FastAPI event loop.

   `backend/app/api/settings.py:222` exposes an async endpoint, but
   `backend/app/api/settings.py:229` synchronously builds and runs
   `RussianTextEnricher`. With heavy NLP stages enabled, one preview can block
   the API process. Run preview in a thread/process or route it through the
   worker path.

6. NLP config revision writes are race-prone.

   `backend/app/infrastructure/persistence/nlp_config_repository.py:30` and
   `backend/app/infrastructure/persistence/nlp_config_repository.py:73` compute
   the next revision as `max(revision) + 1`, then deactivate and insert without
   an advisory lock or serializable transaction. Parallel save/seed/merge calls
   can collide on unique revision/active constraints.

7. The review lane editor is brittle for manual JSON edits.

   `frontend/src/App.tsx:1405` exposes `match_groups JSON`. The controlled input
   parses JSON on every change via `frontend/src/App.tsx:2031`; while the user
   is typing temporarily invalid JSON, the value falls back to the previous
   parsed object. This makes ordinary manual editing unreliable. Keep raw text
   state and validate on blur/save, or provide structured controls.

## Additional Risks

- `frontend/src/App.tsx` is already too large and mixes shell, enrichment,
  settings, review lane editing, dialogs, and rendering helpers. The production
  build emits a 578.14 kB minified JS chunk. Settings and analytics are good
  candidates for lazy loading and component extraction.
- Docker is explicitly development-only: backend runs with `--reload`, frontend
  runs Vite dev server, and source is bind-mounted. This matches
  `docs/architecture.md:5`, but it is not production readiness.
- The worktree contains an untracked `.claude/` directory: 48 files, about 372K.
  It should be intentionally committed, ignored, or removed before opening a PR.
- `state/backlog.md:7` still says "Add initial database migration" even though
  migrations already exist. The backlog is stale.

## Verification

Commands run from this worktree:

- `cd backend && uv run ruff check .` - passed.
- `cd backend && uv run mypy .` - passed, 57 source files.
- `cd backend && uv run pytest -q` - 45 passed, 1 skipped.
- `cd backend && uv run pytest --runslow tests/test_enrichment_pipeline.py::test_enriches_text_with_configured_domain_signal -q` - 1 passed.
- `cd frontend && npm test` - 10 passed.
- `cd frontend && npm run build` - passed; Vite warned about a 578.14 kB chunk.
- `docker compose config` - passed.

Tracked files were clean before this review file was added. The pre-existing
untracked `.claude/` directory remains unrelated to this review.
