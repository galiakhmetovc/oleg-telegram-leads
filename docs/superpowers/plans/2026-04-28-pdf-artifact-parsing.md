# PDF Artifact Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse downloaded PUR PDF artifacts into searchable `parsed_chunks` and schedule parsing automatically after document download.

**Architecture:** Keep parser logic behind the existing `ArtifactParserAdapter` protocol. The runtime `download_artifact` handler records an artifact, then enqueues `parse_artifact` for downloaded PDF documents; the CLI worker wires a built-in PDF parser adapter into the canonical catalog handler registry.

**Tech Stack:** Python 3.12, pypdf, SQLAlchemy Core, existing scheduler/runtime/catalog services.

---

## Scope

This plan parses text PDFs only. It does not OCR scanned PDFs, parse audio, DOCX, XLSX, or run AI extraction into catalog candidates.

## Task 1: PDF Parser Adapter

**Files:**
- Create: `src/pur_leads/integrations/documents/pdf_parser.py`
- Modify: `pyproject.toml`
- Test: `tests/test_document_pdf_parser.py`

- [ ] Write a failing test with a small in-memory/minimal PDF fixture or monkeypatched reader that proves `PdfArtifactParser` returns page-based chunks.
- [ ] Add `pypdf` as a runtime dependency.
- [ ] Implement `PdfArtifactParser.parse_artifact(source_id, artifact_id, payload)` for local PDF paths.
- [ ] Normalize empty pages away and include parser metadata `pypdf`/version.
- [ ] Run focused parser tests.

## Task 2: Runtime Scheduling After Download

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_catalog_runtime_handlers.py`

- [ ] Write a failing test that `download_artifact` enqueues `parse_artifact` after successful PDF download.
- [ ] Ensure audio/video/skipped/unsupported document downloads do not enqueue parser jobs.
- [ ] Implement scheduling with an idempotency key tied to the artifact id.
- [ ] Run focused runtime tests.

## Task 3: CLI Worker Wiring

**Files:**
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_cli.py` or focused runtime wiring test.

- [ ] Write a failing test that `_build_worker_handlers` contains a configured `parse_artifact` handler.
- [ ] Wire the built-in PDF parser into `build_catalog_handler_registry`.
- [ ] Run focused CLI/runtime tests.

## Task 4: Verification, Deploy, And Backfill Parse Existing PDFs

**Files:**
- No additional source files expected.

- [ ] Run `uv run --extra dev ruff check`.
- [ ] Run `uv run --extra dev ruff format --check`.
- [ ] Run `uv run --extra dev mypy src`.
- [ ] Run `uv run --extra dev pytest -q`.
- [ ] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out` and report only line count.
- [ ] Commit and push to `main`.
- [ ] Deploy on `teamd-ams1`, restart web/worker, and verify `/health` plus `docker compose ps web worker`.
- [ ] Mark existing audio artifacts as skipped/audio and remove their downloaded files.
- [ ] Enqueue `parse_artifact` for the 3 existing downloaded PDFs and verify `parsed_chunks` increases.
