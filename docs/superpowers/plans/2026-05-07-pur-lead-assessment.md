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

- [x] Write failing tests for hot/warm/non-lead scoring using synthetic `DomainSignal` and `ExtractedFact` inputs.
- [x] Add `LeadTemperature`, `LeadReason`, `LeadAssessment`, and config dataclasses.
- [x] Parse `lead_scoring` documents with thresholds, weights, solution mappings, segment mappings, and noise mappings.
- [x] Implement `LeadScorer.assess(signals, facts)` with deterministic score, temperature, areas, segments, reasons, and noise.
- [x] Run `cd backend && uv run pytest tests/test_lead_scorer.py`.
- [x] Commit backend scoring core.

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

- [x] Write failing regression tests that current lead examples return `lead_assessment.is_lead == true`.
- [x] Add the `lead_scoring` pipeline stage and progress callback message.
- [x] Load `lead_scoring.yaml` as bootstrap config and include it in DB revisions.
- [x] Expand PUR taxonomy rules from the brief using Yargy phrases/patterns, not regex.
- [x] Run focused backend pipeline/config tests.
- [x] Commit pipeline integration.

## Task 3: Settings API And UI

**Files:**
- Modify: `backend/app/api/settings.py`
- Modify: `backend/tests/test_settings_api.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [x] Write failing settings API tests proving `lead_scoring` is returned, previewed, and saved as a DB revision.
- [x] Extend settings schemas for lead scoring without changing YAML directly.
- [x] Add UI types for `lead_assessment` and lead scoring settings.
- [x] Render lead verdict, score, temperature, solution areas, customer segments, reasons, and noise on the overview tab.
- [x] Add Settings Center section for editable thresholds, weights, and mappings.
- [x] Run focused backend settings tests and frontend tests.
- [x] Commit API/UI settings work.

## Task 4: Runtime Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`
- Modify: `state/current.md`

- [x] Apply migration/config revision in dev by saving the current settings through the API after code loads the new bootstrap shape.
- [x] Run full backend checks: `uv run ruff check .`, `uv run mypy .`, `uv run pytest`.
- [x] Run full frontend checks: `npm test -- --run`, `npm run build`.
- [x] Run infra check: `docker compose config`.
- [x] Runtime smoke through Caddy with at least the smart-home, Zigbee, video-surveillance, and leak-sensor examples.
- [x] Update docs and current state with the lead assessment contract.
- [x] Commit final docs/runtime evidence.

## Deferred Task 5: Batch Enrichment Optimization Plan

**Status:** Planned, not started. Do not implement this until the user explicitly resumes batch throughput work.

**Baseline:**
- Dataset: `artifacts/designer-channel/messages.jsonl`, 528953 text messages.
- Current full-enrichment benchmark on the first 300 messages: 65.31 seconds,
  4.59 messages/sec, 0 failures, 6 leads, peak RSS about 1.34 GB, output 1.9 MB.
- Linear one-process estimate for the full dataset: about 32 hours and about
  3.24 GiB uncompressed JSONL output.
- Host constraints observed on 2026-05-07: 8 CPU cores, about 11 GiB RAM, about
  6.9 GiB free disk on `/` after cleanup. Four processes probably fit in RAM,
  but CPU oversubscription and disk pressure must be measured before using them.

**Optimization candidates to implement later:**
- Add resumable result caching keyed by `message_id`, `text_hash`, and active
  `config_hash`, so interrupted full runs can continue without recomputing
  unchanged messages.
- Add duplicate-text caching keyed by `text_hash`, because Telegram exports can
  contain repeated or forwarded text. Reuse the full enrichment result only when
  the active config hash matches.
- Add sharded batch execution, for example `--shard-index` and `--shard-count`,
  so multiple independent processes can safely write separate output files.
- Add streaming compressed output, preferably `.jsonl.zst`, before running the
  whole dataset. Full uncompressed output is too large for the current disk
  margin.
- Benchmark 1, 2, and 4 process runs after sharding and compression are in
  place. Pin heavy numeric/model thread pools with `OMP_NUM_THREADS=1`,
  `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1` during those benchmarks.
- Add cheap rule gating before Yargy fact/signal parsers: use configured anchor
  words or lemmas to skip irrelevant rule groups without hardcoding PUR business
  logic in Python.
- Consider a word/lemma cache only as a later, carefully tested optimization.
  Natasha morphology, tagging, and syntax are contextual; a naive per-word cache
  must not replace contextual enrichment where it affects quality.

**Decision for now:** Keep the current full enrichment behavior. Do not trade
quality for speed; optimize execution, caching, output format, and parallelism
around the complete pipeline.
