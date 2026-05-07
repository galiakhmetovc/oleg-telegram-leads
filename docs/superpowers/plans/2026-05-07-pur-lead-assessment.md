# PUR Lead Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explainable deterministic lead assessment layer for PUR text analysis.

**Architecture:** Keep the existing enrichment pipeline, but add a domain-level `lead_assessment` result computed from configured facts and domain signals. Business taxonomy, weights, thresholds, and rule mappings live in NLP config revisions stored in PostgreSQL; YAML files are bootstrap defaults only.

**Tech Stack:** Python 3.12, FastAPI, Natasha, Yargy, SQLAlchemy/PostgreSQL JSONB, React, Vite, TypeScript, MUI.

---

## File Structure

- Modify `backend/app/domain/enrichment.py`: add lead assessment dataclasses and serialization.
- Modify `backend/app/infrastructure/nlp/config_loader.py`: parse `lead_scoring` config.
- Create `backend/app/infrastructure/nlp/lead_scorer.py`: deterministic scoring engine.
- Modify `backend/app/infrastructure/nlp/russian_text_enricher.py`: run scoring after facts/signals.
- Add `backend/config/nlp/lead_scoring.yaml`: bootstrap taxonomy, weights, thresholds.
- Modify `backend/config/nlp/pipeline.yaml`: add `lead_scoring` stage.
- Modify `backend/config/nlp/signals.yaml` and `backend/config/nlp/facts.yaml`: expand PUR rules from the brief.
- Modify `backend/app/api/settings.py` and `backend/tests/test_settings_api.py`: expose and validate lead scoring settings.
- Modify `frontend/src/App.tsx` and `frontend/src/App.test.tsx`: render lead verdict and editable scoring settings.
- Add/modify backend tests for scoring, pipeline regression, and config validation.
- Update `README.md`, `docs/architecture.md`, `docs/decisions.md`, `state/current.md`.

## Task 1: Backend Domain And Scoring

**Files:**
- Modify: `backend/app/domain/enrichment.py`
- Modify: `backend/app/infrastructure/nlp/config_loader.py`
- Create: `backend/app/infrastructure/nlp/lead_scorer.py`
- Test: `backend/tests/test_lead_scorer.py`

- [ ] Write failing tests for hot/warm/non-lead scoring using synthetic `DomainSignal` and `ExtractedFact` inputs.
- [ ] Add `LeadTemperature`, `LeadReason`, `LeadAssessment`, and config dataclasses.
- [ ] Parse `lead_scoring` documents with thresholds, weights, solution mappings, segment mappings, and noise mappings.
- [ ] Implement `LeadScorer.assess(signals, facts)` with deterministic score, temperature, areas, segments, reasons, and noise.
- [ ] Run `cd backend && uv run pytest tests/test_lead_scorer.py`.
- [ ] Commit backend scoring core.

## Task 2: Pipeline Integration And Bootstrap Config

**Files:**
- Modify: `backend/app/infrastructure/nlp/russian_text_enricher.py`
- Modify: `backend/app/infrastructure/nlp/config_loader.py`
- Modify: `backend/config/nlp/pipeline.yaml`
- Modify: `backend/config/nlp/signals.yaml`
- Modify: `backend/config/nlp/facts.yaml`
- Add: `backend/config/nlp/lead_scoring.yaml`
- Test: `backend/tests/test_enrichment_pipeline.py`
- Test: `backend/tests/test_enrichment_config.py`

- [ ] Write failing regression tests that current lead examples return `lead_assessment.is_lead == true`.
- [ ] Add the `lead_scoring` pipeline stage and progress callback message.
- [ ] Load `lead_scoring.yaml` as bootstrap config and include it in DB revisions.
- [ ] Expand PUR taxonomy rules from the brief using Yargy phrases/patterns, not regex.
- [ ] Run focused backend pipeline/config tests.
- [ ] Commit pipeline integration.

## Task 3: Settings API And UI

**Files:**
- Modify: `backend/app/api/settings.py`
- Modify: `backend/tests/test_settings_api.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] Write failing settings API tests proving `lead_scoring` is returned, previewed, and saved as a DB revision.
- [ ] Extend settings schemas for lead scoring without changing YAML directly.
- [ ] Add UI types for `lead_assessment` and lead scoring settings.
- [ ] Render lead verdict, score, temperature, solution areas, customer segments, reasons, and noise on the overview tab.
- [ ] Add Settings Center section for editable thresholds, weights, and mappings.
- [ ] Run focused backend settings tests and frontend tests.
- [ ] Commit API/UI settings work.

## Task 4: Runtime Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`
- Modify: `state/current.md`

- [ ] Apply migration/config revision in dev by saving the current settings through the API after code loads the new bootstrap shape.
- [ ] Run full backend checks: `uv run ruff check .`, `uv run mypy .`, `uv run pytest`.
- [ ] Run full frontend checks: `npm test -- --run`, `npm run build`.
- [ ] Run infra check: `docker compose config`.
- [ ] Runtime smoke through Caddy with at least the smart-home, Zigbee, video-surveillance, and leak-sensor examples.
- [ ] Update docs and current state with the lead assessment contract.
- [ ] Commit final docs/runtime evidence.
