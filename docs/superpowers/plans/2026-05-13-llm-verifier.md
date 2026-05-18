# LLM Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local LLM verifier that audits deterministic Telegram lead enrichment using active taxonomy and selected golden examples.

**Architecture:** Backend-first vertical slice. The application builds a compact context pack, calls an LLM client interface, validates strict JSON, and persists the verification run separately from deterministic lead status.

**Tech Stack:** FastAPI, SQLAlchemy Core, Alembic, Pydantic, Ollama-compatible HTTP API, pytest.

---

### Task 1: Context Pack And Schema

**Files:**
- Create: `backend/app/domain/llm_verification.py`
- Create: `backend/app/application/llm_verification/context.py`
- Test: `backend/tests/test_llm_verification_context.py`

- [ ] Write failing tests for context pack construction from message, enrichment result, active config, and golden examples.
- [ ] Implement domain dataclasses and response schema validation.
- [ ] Implement taxonomy extraction from active NLP config documents.
- [ ] Implement simple golden selection using verdict balance and overlap with facts/signals/text.
- [ ] Run targeted tests.

### Task 2: Persistence

**Files:**
- Modify: `backend/app/infrastructure/persistence/tables.py`
- Create: `backend/alembic/versions/0033_llm_verifications.py`
- Create: `backend/app/infrastructure/persistence/llm_verification_repository.py`
- Test: `backend/tests/test_llm_verification_repository.py`

- [ ] Write failing repository tests for create/list verification runs.
- [ ] Add `llm_verifications` table metadata and migration.
- [ ] Implement repository methods.
- [ ] Run targeted tests.

### Task 3: LLM Client And Use Case

**Files:**
- Create: `backend/app/application/llm_verification/use_cases.py`
- Create: `backend/app/application/llm_verification/ports.py`
- Create: `backend/app/infrastructure/llm/ollama_client.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_llm_verification_use_cases.py`

- [ ] Write failing tests for successful valid JSON and invalid JSON failure storage.
- [ ] Add settings for enabled flag, endpoint, model, timeout.
- [ ] Implement Ollama-compatible client using JSON schema `format`.
- [ ] Implement `VerifySourceMessageWithLlm` use case.
- [ ] Run targeted tests.

### Task 4: API

**Files:**
- Create: `backend/app/api/llm_verifications.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_llm_verifications_api.py`

- [ ] Write failing API tests for POST run, GET list, and 404 missing source message.
- [ ] Add dependencies and routes.
- [ ] Serialize verification runs.
- [ ] Run targeted API tests.

### Task 5: Verification

**Files:**
- Update docs as needed.

- [ ] Run backend targeted LLM verifier tests.
- [ ] Run full backend test suite if feasible.
- [ ] Run `git diff --check`.
