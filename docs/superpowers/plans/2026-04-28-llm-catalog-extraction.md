# LLM Catalog Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable LLM catalog extractor so PUR messages/documents produce richer catalog candidates before lead fuzzy matching runs.

**Architecture:** Keep the existing scheduler and `extract_catalog_facts` runtime path. Add a small chat-completion port, a Z.AI-compatible client configured for the Coding endpoint, and an LLM catalog extractor that returns existing `CatalogExtractedFact` DTOs. After successful candidate creation, rebuild the classifier snapshot so the fuzzy classifier immediately sees new `auto_pending` catalog knowledge.

**Tech Stack:** Python 3.12, httpx, SQLAlchemy, existing SQLite catalog tables, pytest/pytest-asyncio.

---

### Task 1: LLM Extractor Contract And Parser

**Files:**
- Create: `src/pur_leads/integrations/catalog/llm_extractor.py`
- Test: `tests/test_llm_catalog_extractor.py`

- [x] Write failing tests for strict JSON fact extraction from a fake chat client.
- [x] Verify the tests fail because the LLM extractor does not exist.
- [x] Implement prompt construction, JSON extraction, fact validation, candidate-type mapping, and quote preservation.
- [x] Run focused extractor tests and verify they pass.

### Task 2: Z.AI Chat Client

**Files:**
- Create: `src/pur_leads/integrations/ai/chat.py`
- Create: `src/pur_leads/integrations/ai/zai_client.py`
- Create: `src/pur_leads/integrations/ai/__init__.py`
- Test: `tests/test_zai_chat_client.py`

- [x] Write failing tests with `httpx.MockTransport` for endpoint, auth header, payload, response usage, and provider errors.
- [x] Verify the tests fail because the client does not exist.
- [x] Implement the async chat client against `/chat/completions`.
- [x] Run focused client tests and verify they pass.

### Task 3: Runtime Metadata And Snapshot Rebuild

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_catalog_runtime_handlers.py`

- [x] Write failing tests proving extraction runs store LLM metadata/token usage and rebuild classifier snapshots after new candidates.
- [x] Verify the tests fail.
- [x] Start extraction runs before adapter calls, finish failed runs on adapter errors, persist token usage, and rebuild snapshots after candidate changes.
- [x] Run focused runtime tests and verify they pass.

### Task 4: CLI/Worker Wiring And Settings

**Files:**
- Modify: `src/pur_leads/core/config.py`
- Modify: `src/pur_leads/services/settings.py`
- Modify: `src/pur_leads/cli.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Test: `tests/test_cli.py`

- [x] Write failing tests proving the worker chooses LLM extraction when enabled and a Z.AI key is configured, otherwise keeps heuristic extraction.
- [x] Verify the tests fail.
- [x] Add settings/env defaults and wire `LlmCatalogExtractor` with `ZaiChatCompletionClient`.
- [x] Run focused CLI tests and verify they pass.

### Task 5: Verification, Push, Deploy

**Files:**
- Modify plan checklist only after verification.

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `node --check src/pur_leads/web/static/app.js`.
- [x] Run `TMPDIR=/home/admin/AI-AGENT/data/tmp/oleg-telegram-leads-pytest uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out && wc -l /tmp/oleg-telegram-leads-compose.out`.
- [x] Commit and push `main`.
- [x] Deploy on `teamd-ams1`, run migrations if needed, restart web/worker, and verify `/health`.
