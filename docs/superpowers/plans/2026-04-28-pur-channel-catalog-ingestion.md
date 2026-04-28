# PUR Channel Catalog Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Telegram polling for catalog-enabled sources to the catalog source-of-truth tables and document artifact downloader.

**Architecture:** Keep Telegram collection and catalog extraction layered. Polling stores `source_messages`, mirrors catalog-enabled messages into `sources` plus text `parsed_chunks`, and enqueues bounded document-download jobs; the downloader fetches only document media through the Telegram client port and records `artifacts`.

**Tech Stack:** Python 3.12, SQLAlchemy Core, SQLite, Telethon 1.43, pytest, existing scheduler/runtime.

---

## Scope

This plan implements the ingestion bridge from Telegram messages into raw catalog sources and downloaded document artifacts. It does not implement PDF/DOC/XLS parsing or AI catalog extraction; those remain downstream parser/extractor adapters.

## Task 1: Catalog Source Mirroring From Telegram Polling

**Files:**
- Modify: `src/pur_leads/workers/telegram_polling.py`
- Test: `tests/test_telegram_polling_jobs.py`

- [ ] Write a failing test that a `catalog_ingestion` source poll creates a `sources` row with `source_type="telegram_message"`, stores one text chunk from message text/caption, links `source_messages.raw_source_id`, and enqueues `download_artifact` for downloadable document media.
- [ ] Run the test and verify it fails because polling currently only stores `source_messages`.
- [ ] Implement catalog mirroring for `catalog_ingestion_enabled` sources only.
- [ ] Run the focused polling tests and verify they pass.

## Task 2: Telegram Document Metadata And Download Port

**Files:**
- Modify: `src/pur_leads/integrations/telegram/types.py`
- Modify: `src/pur_leads/integrations/telegram/client.py`
- Modify: `src/pur_leads/integrations/telegram/telethon_client.py`
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_telethon_client_adapter.py`
- Test: `tests/test_telegram_client_port.py`

- [ ] Write failing tests that Telethon marks document messages as downloadable, marks video documents as skipped, and can download a document to a supplied directory.
- [ ] Run the focused tests and verify they fail on missing metadata/download method.
- [ ] Add `TelegramDocumentDownload` DTO and `download_message_document` to the client port.
- [ ] Implement Telethon document metadata extraction and `download_media(message, file=directory)` based document download.
- [ ] Run the focused Telegram adapter tests and verify they pass.

## Task 3: Runtime `download_artifact` Handler

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Modify: `src/pur_leads/core/config.py`
- Test: `tests/test_catalog_runtime_handlers.py`

- [ ] Write a failing test that a `download_artifact` job records a downloaded document artifact with local path and sha256.
- [ ] Write a failing test that a skipped video/non-document result records a skipped artifact with a skip reason.
- [ ] Run the focused runtime tests and verify they fail because no handler exists.
- [ ] Implement the handler in the canonical worker registry, deriving monitored source and message id from the job payload.
- [ ] Add configurable `artifact_storage_path` with a local default under `data/artifacts`.
- [ ] Run the focused runtime tests and verify they pass.

## Task 4: Verification And Deploy

**Files:**
- No new files expected beyond the code/test changes above.

- [ ] Run `uv run --extra dev ruff check`.
- [ ] Run `uv run --extra dev ruff format --check`.
- [ ] Run `uv run --extra dev mypy src`.
- [ ] Run `uv run --extra dev pytest -q`.
- [ ] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out` and report only line count.
- [ ] Commit and push to `main`.
- [ ] Deploy on `teamd-ams1`, restart web/worker, and verify `/health` plus `docker compose ps web worker`.
