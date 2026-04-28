# Heuristic Catalog Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn parsed PUR text chunks into structured `extracted_facts` and `catalog_candidates` without waiting for the later AI extractor.

**Architecture:** Add a replaceable built-in extractor adapter behind the existing `CatalogExtractorAdapter` protocol. It reads `parsed_chunks`, extracts conservative service/solution/offer candidates from known PUR catalog layouts, and the existing runtime handler persists facts/candidates/evidence.

**Tech Stack:** Python 3.12, SQLAlchemy Core, existing catalog runtime/candidate services, pytest.

---

## Scope

This is not the final AI extractor. It is a deterministic bootstrap extractor for current PUR PDF text: numbered services like `1.1 Управление освещением...` and boxed access-control solutions like `Уровень 3 - Начальный`.

## Task 1: Heuristic Extractor Adapter

**Files:**
- Create: `src/pur_leads/integrations/catalog/__init__.py`
- Create: `src/pur_leads/integrations/catalog/heuristic_extractor.py`
- Test: `tests/test_heuristic_catalog_extractor.py`

- [x] Write a failing direct adapter test for numbered service rows.
- [x] Write a failing direct adapter test for access-control solution/price rows.
- [x] Implement chunk loading, numbered service parsing, category inference, term generation, and evidence quotes.
- [x] Run focused extractor tests.

## Task 2: Runtime Extraction Scheduling

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_catalog_runtime_handlers.py`

- [x] Write a failing test that `parse_artifact` enqueues one `extract_catalog_facts` job per parsed chunk.
- [x] Implement idempotent scheduling after chunk replacement.
- [x] Run focused runtime tests.

## Task 3: CLI Worker Wiring

**Files:**
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_cli.py`

- [x] Write a failing test that CLI `worker once` can process `extract_catalog_facts` without external adapter injection.
- [x] Wire `HeuristicCatalogExtractor(session)` into `build_catalog_handler_registry`.
- [x] Run focused CLI/runtime tests.

## Task 4: Verification, Deploy, And Backfill

**Files:**
- No additional source files expected.

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out` and report only line count.
- [x] Commit and push to `main`.
- [x] Deploy on `teamd-ams1`, restart web/worker, and verify `/health` plus `docker compose ps web worker`.
- [x] Enqueue extraction for existing parsed chunks and verify candidates/facts appear.
