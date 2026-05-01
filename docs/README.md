# PUR Leads Documentation Index

Last audited: 2026-05-01.

This is the main entry point for project documentation. Treat this file as the
current map of what is implemented, what is partial, and which secondary
documents contain the detailed design.

## Reading Order

1. `README.md` - quick project summary, local commands, production pointer.
2. `docs/README.md` - current implementation status and documentation map.
3. `docs/operations/artifacts-and-production.md` - production deployment and artifact UI runbook.
4. `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md` - full product target.
5. `docs/superpowers/specs/2026-04-30-continuous-telegram-ingest-chat-analytics-design.md` - Telegram raw/analytics target.
6. `docs/superpowers/plans/2026-04-30-source-agnostic-catalog-ingest-plan.md` - source-agnostic evidence/catalog ingest plan.
7. `docs/superpowers/plans/2026-04-30-catalog-llm-trace-prompts.md` - prompt/trace/catalog rebuild target.

The specs and plans are intentionally broader than the current code. When they
conflict with this document, this document describes the current codebase state;
the specs describe the target direction.

## Current Product Shape

PUR Leads is a FastAPI/SQLite application for:

- collecting Telegram/public-channel history and documents into a reusable raw layer;
- normalizing and indexing that raw layer for search and analytics;
- building catalog knowledge and lead examples with review/audit;
- detecting and reviewing lead candidates;
- operating lightweight CRM, quality, resources, settings, and production visibility screens.

Telegram is treated as a source and urgent notification channel. The web UI is
the operator workspace.

## Implemented

Core application:

- SQLite/Alembic foundation through migration `0026_entity_enrichment_registry`.
- FastAPI web app with bootstrap local admin, Telegram-admin account support, resources, settings, AI registry, task executors, quality, operations, sources, catalog, CRM, leads, and artifacts pages.
- Material Web assets are vendored locally; custom CSS is used for layout and product composition.
- Worker runtime with scheduler jobs, retry/defer behavior, exponential backoff, `Retry-After` handling, and configurable worker concurrency.
- Resource capacity report for worker slots, AI model pools, Telegram userbots, Telegram bots, local parser capacity, and external fetch capacity.

Telegram source and raw acquisition:

- Sources can be created through the web UI and can use `from_now`, `recent_days`, `from_message`, and `from_beginning`.
- `export_telegram_raw` job type exists for explicit reusable history acquisition.
- Telethon-based raw export writes one reusable acquisition run to:
  - `result.json`;
  - `messages.jsonl`;
  - `attachments.jsonl`;
  - `messages_raw.parquet`;
  - `attachments_raw.parquet`;
  - `manifest.json`.
- `telegram_raw_export_runs` tracks paths, counts, status, source identity, and stage metadata.
- Raw export supports configurable ranges and media policy through source/job payloads.
- When media is skipped or unavailable, metadata remains in the raw rows so downstream stages can still see that an attachment existed.
- Telegram Desktop JSON zip import is supported and writes into the same raw export model.

Chat analytics pipeline:

- Stage 1 EDA: `pur-leads analyze telegram-eda`.
  Produces `eda_summary.json` with message counts, author counts, text/url/reaction ratios, PII ratio, duplicate ids, future-date anomalies, and a human GO/NO-GO placeholder.
- Stage 2 text normalization: `pur-leads analyze telegram-texts`.
  Produces `texts.parquet` with raw text, clean text, language, tokens, lemmas, POS tags, token map, status, and raw message JSON.
- Artifact text extraction: `pur-leads analyze telegram-artifacts`.
  Parses external pages and downloaded text/PDF-like documents into normalized artifact text rows with parent Telegram identity. External fetch and document parsing have concurrency and timeout settings, defaulting to 10-minute timeouts.
- FTS index: `pur-leads analyze telegram-fts`.
  Indexes message text and artifact chunks in SQLite FTS5.
- Chroma index: `pur-leads analyze telegram-chroma`.
  Builds a local persistent Chroma index over messages and artifact chunks. `rubert_tiny2_v1` is the intended Russian embedding profile when optional embedding dependencies are installed; `local_hashing_v1` is available as deterministic local fallback.
- Unified search: `pur-leads search telegram`.
  Merges FTS and Chroma hits and returns source-backed RAG context with Telegram message links and artifact metadata.
- Stage 3 features: `pur-leads analyze telegram-features`.
  Combines message and artifact normalized text, detects question/offer/solution-like signals, prices, phones, emails, Telegram usernames, URLs, technical-language scores, quality signals, and traceable source identity. Domain profiles are reserved but disabled.
- Stage 4 aggregated stats: `pur-leads analyze telegram-stats`.
  Produces aggregate stats, n-grams, entity candidates, URL summary, source quality, and message/artifact row counts.
- Stage 5 entity extraction: `pur-leads analyze telegram-entities`.
  Extracts candidates from POS patterns and creates exact entity groups plus fuzzy/translit review candidates.
- Stage 5.1 entity ranking: `pur-leads analyze telegram-entity-ranking`.
  Adds transparent rule-based score, status, reasons, penalties, ranked JSON, and noise report. No AI and no domain profiles are applied.
- Stage 5.2 entity enrichment: `pur-leads analyze telegram-entity-enrichment`.
  Uses either rule-based fallback or LLM to map ranked entities into a canonical registry. It stores prompt text, request JSON, response JSON, parsed response, context snapshot, provider/model/profile, and source refs. Writes `auto_pending` canonical entities and merge-review candidates, not approved catalog truth.

Catalog and examples:

- Manual catalog editor exists for items, terms, offers, attributes, evidence, archive/update flows, and classifier snapshot rebuild.
- Manual catalog/lead/non-lead/maybe input can store raw source material without automatically running extraction.
- Catalog candidate review and quality-review foundations exist.
- Idle catalog candidate validation is implemented as a scheduler concept for using strong models when realtime/normal/bulk work is idle.

Lead candidate research:

- `pur-leads analyze telegram-lead-candidates` scans prepared FTS indexes and writes review-only lead candidates. It does not create operational leads or notifications.
- `pur-leads analyze telegram-lead-candidate-llm` runs review-only LLM arbitration over candidates and writes full prompt/response traces to artifacts. It does not mutate CRM leads.

AI/resource layer:

- Z.AI provider, model seed, model limits, capabilities, agents, model profiles, and task executor routes exist.
- Limits are modeled per provider account + model, using 80% utilization by default with `max(1, floor(limit * ratio))`.
- Model profiles include max input/output tokens, temperature, thinking mode, structured-output requirement, response format, and provider options.
- Z.AI capability differences are represented: thinking support, structured output, vision/document flags, OCR endpoint family.
- AI routes support primary, fallback, shadow, and task-specific executor binding.

Observability and operations:

- `/operations` and `/api/operations/*` expose jobs, runs, events, capacity, backup/restore, quality, access checks, notifications, and audit summaries.
- `/artifacts` and `/api/artifacts/*` expose generated files from raw export runs and stage metadata, including bounded filesystem discovery under artifact directories.
- Artifact previews support JSON, JSONL, text, directories, Parquet, and SQLite.
- Production runbook and rollback notes are documented in `docs/operations/artifacts-and-production.md`.

## Partially Implemented

- Source-agnostic evidence model exists in documentation and some API pieces, but there is no complete unified `Evidence` UI for manual uploads, Telegram messages, documents, chunks, scope review, promotion actions, and privacy warnings.
- Manual text/catalog-note input exists; full manual arbitrary document upload into the same evidence graph is not yet productized.
- Stage 6 thread reconstruction exists only as thread/reply fields used by search and lead candidate context. There is no standalone `threads.parquet` stage yet.
- OCR is represented in AI registry and documentation, but scanned-PDF/image OCR via `GLM-OCR` is not wired as a complete parse fallback.
- Prompt/LLM trace exists for entity enrichment and review-only lead arbitration, but a unified prompt registry, prompt editor, and generic AI trace viewer are not implemented end-to-end.
- Some CLI paths still accept explicit provider/model/profile options or legacy catalog LLM settings. The target is to route all model work through AI registry task executors.
- Circuit breaker and adaptive p95 timeout settings/help text are documented and exposed as configuration placeholders, but the full runtime breaker/adaptive-timeout behavior is not enforced everywhere yet.
- Chroma runs embedded/local in-process. A separate Chroma server is not part of the current implementation.
- Production has had the Artifacts UI deployed and verified, but the worker was intentionally left stopped for UI-only deployment.

## Not Implemented Yet

- Stage 8 topic modeling.
- Stage 9 QA/FAQ detection.
- Stage 10 knowledge synthesis reports.
- Full source-agnostic evidence UI and promotion workflow.
- Full catalog extraction/rebuild flow from raw chunks through prompt registry, AI trace, candidate diff, and approved catalog mutation.
- Full operational use of `ai_runs` / `ai_run_outputs` for every AI call.
- Live Telegram listener; current runtime is polling/catchup plus explicit raw export jobs.
- S3-compatible archive/backup backend.
- Scoped web roles beyond `admin`.
- Complete semantic/vector matching in operational lead detection. Chroma search exists for analytics/RAG; lead detection still relies on catalog/fuzzy/optional shadow flows.

## New Since The Initial Spec

- Raw Telegram acquisition was made reusable: one Telethon read can be replayed through Parquet, text normalization, artifacts, FTS, Chroma, entity extraction, lead-candidate research, and later AI stages.
- Telegram Desktop zip import was added as an alternate ingestion source for user-exported chat history.
- Stage 5.1 rule-based entity ranking was added to clean and prioritize noisy POS entities before LLM.
- Stage 5.2 canonical entity enrichment was added with persistent registry context between LLM calls, preventing independent requests from inventing duplicate canonical names silently.
- Review-only lead candidate discovery and LLM arbitration were added to inspect lead quality without creating live leads.
- Artifact visibility UI was added so raw exports, Parquet, SQLite FTS, Chroma internals, JSON traces, and summaries can be inspected from the web UI.
- Resource/capacity planning was broadened to provider accounts, model profiles, Telegram userbots, ordinary bots, parser/fetch pools, worker concurrency, and idle validation.

## Documentation Map

Primary product target:

- `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`

Telegram raw/analytics target:

- `docs/superpowers/specs/2026-04-30-continuous-telegram-ingest-chat-analytics-design.md`

Catalog/evidence plans:

- `docs/superpowers/plans/2026-04-30-source-agnostic-catalog-ingest-plan.md`
- `docs/superpowers/plans/2026-04-30-catalog-llm-trace-prompts.md`

Operations:

- `docs/operations/artifacts-and-production.md`

Older implementation plans under `docs/superpowers/plans/2026-04-28-*` and
`docs/superpowers/plans/2026-04-29-*` are historical task plans. Use them for
why a slice was built, not as the current status source.

## Next Architectural Priorities

1. Make the source-agnostic evidence UI the product-visible raw layer:
   raw source, message/document/page, parsed chunks, scope, parser status,
   privacy flags, and promotion actions.
2. Unify prompt management and AI trace visibility:
   prompt version, model profile, request, response, parsed result, token/context
   usage, retries, fallback route, and catalog mutation diff.
3. Finish catalog rebuild:
   raw evidence -> ranked entities/chunks -> AI/rule extraction -> candidates ->
   review -> operational catalog snapshot.
4. Move remaining AI calls onto AI registry task executors and shared trace/lease policy.
5. Add OCR fallback for scanned documents and wire it through the same artifact/chunk model.
6. Only after the raw/catalog trace is strong, consider topic/QA/knowledge synthesis.
