# Catalog Source Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SQLite source-of-truth foundation for PUR raw sources, artifacts, parsed chunks, catalog candidates, operational catalog rows, evidence, manual inputs, and classifier snapshots.

**Architecture:** Keep ingestion layered: immutable `sources`, optional `artifacts`, searchable `parsed_chunks`, auditable extraction/candidate rows, then operational catalog rows. Services should be deterministic and testable without live Telegram or AI; runtime jobs and real parsers can call the same services later.

**Tech Stack:** Python 3.12, SQLAlchemy Core, Alembic, SQLite/FTS5, pytest, existing scheduler/audit/settings foundation.

---

## Scope

This plan implements catalog/source storage and deterministic catalog mutation services. It does not implement live PUR channel download, document parsing libraries, AI extraction, lead detection, CRM, or web screens.

## Task 1: Catalog Source Schema

- [x] Implement migration/model tables and verify migration/FTS tests.

**Files:**
- Create: `migrations/versions/0003_catalog_source_foundation.py`
- Create: `src/pur_leads/models/catalog.py`
- Test: `tests/test_catalog_source_migration.py`

- [ ] Add tables: `sources`, `artifacts`, `parsed_chunks`, `extraction_runs`, `catalog_versions`, `extracted_facts`, `catalog_candidates`, `catalog_candidate_facts`, `catalog_categories`, `catalog_items`, `catalog_terms`, `catalog_attributes`, `catalog_offers`, `catalog_relations`, `catalog_evidence`, `manual_inputs`, `classifier_examples`, `classifier_versions`, `classifier_snapshot_entries`, `classifier_version_artifacts`.
- [ ] Add unique indexes for source identity, parsed chunk order, category slug, item canonical name, term normalized identity, evidence dedupe, and classifier version.
- [ ] Add FTS5 virtual table/triggers for `parsed_chunks.text`.
- [ ] Verify migration creates all tables, constraints reject invalid statuses/types, and FTS returns inserted chunks.

## Task 2: Raw Source And Manual Input Services

**Files:**
- Create: `src/pur_leads/repositories/catalog_sources.py`
- Create: `src/pur_leads/services/catalog_sources.py`
- Test: `tests/test_catalog_source_service.py`

- [ ] Implement immutable-ish source upsert by `(source_type, origin, external_id)` with `content_hash` and normalized text.
- [ ] Implement parsed chunk creation with deterministic chunk indexes and token estimates.
- [ ] Implement artifact metadata recording for downloaded/skipped/failed documents/media.
- [ ] Implement manual input submission and conversion to source/evidence/candidate path for `manual_text`, `manual_link`, catalog facts, lead examples, non-lead examples, and catalog notes.
- [ ] Require manual evidence note by default and allow admin/Oleg manual catalog facts to default to `approved` where direct approval is explicitly requested.
- [ ] Record audit entries for manual source creation and manual input processing.

## Task 3: Catalog Candidate And Evidence Services

**Files:**
- Create: `src/pur_leads/repositories/catalog_candidates.py`
- Create: `src/pur_leads/services/catalog_candidates.py`
- Test: `tests/test_catalog_candidate_service.py`

- [ ] Implement extraction run creation/finish with counters and token usage metadata.
- [ ] Implement extracted fact storage.
- [ ] Implement candidate dedupe by candidate type + canonical name + normalized payload.
- [ ] Link facts to candidates through `catalog_candidate_facts`.
- [ ] Attach evidence rows to candidates/facts with quote/chunk/source references.
- [ ] Default candidate status to `auto_pending`, but force low-confidence, conflicting, too-broad, and noisy-term candidates to `needs_review`.
- [ ] For offer/price candidates, default to `needs_review` unless explicit validity or configured TTL allows `auto_pending`.

## Task 4: Operational Catalog Mutation

**Files:**
- Create: `src/pur_leads/repositories/catalog.py`
- Create: `src/pur_leads/services/catalog.py`
- Test: `tests/test_catalog_service.py`

- [ ] Seed initial top-level categories idempotently.
- [ ] Promote approved/auto-pending candidates into `catalog_items`, `catalog_terms`, `catalog_attributes`, `catalog_offers`, and `catalog_relations`.
- [ ] Promote `lead_phrase` and `negative_phrase` candidates into catalog terms and optional classifier examples so they can affect lead detection without becoming products.
- [ ] Preserve evidence links for every promoted row.
- [ ] Keep item and term statuses independent so noisy terms can be rejected without rejecting items.
- [ ] Generate compact catalog versions with counts, included statuses, and hashes.

## Task 5: Classifier Snapshot Builder

**Files:**
- Create: `src/pur_leads/services/classifier_snapshots.py`
- Test: `tests/test_classifier_snapshot_service.py`

- [ ] Build classifier versions from included catalog statuses.
- [ ] Store explicit snapshot entries for categories/items/terms/attributes/offers/examples.
- [ ] Store classifier version artifacts for catalog prompt text, keyword index, settings snapshot, and token estimate.
- [ ] Verify `auto_pending` and `approved` are included by default while rejected/muted/deprecated/expired are excluded.

## Task 6: Runtime Handler Registration

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_catalog_runtime_handlers.py`

- [ ] Add deterministic handlers for `extract_catalog_facts` and `parse_artifact` when parser/extractor adapters are injected.
- [ ] Verify `parse_artifact` and `extract_catalog_facts` are already accepted by scheduler job-type validation before registering handlers.
- [ ] Unsupported parser/extractor adapters must fail the job visibly through the existing scheduler event path.
- [ ] Keep real AI and document parser implementation outside this plan; tests use fake adapters.

## Acceptance

Run:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src
docker compose config
```
