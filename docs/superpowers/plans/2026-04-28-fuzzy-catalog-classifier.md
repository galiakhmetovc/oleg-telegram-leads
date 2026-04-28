# Fuzzy Catalog Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make saved monitored-source messages classify into Leads Inbox using the active SQLite catalog before the external AI classifier is introduced.

**Architecture:** Keep the existing lead runtime handler and add a built-in classifier adapter. Classifier snapshots include approved/auto-pending catalog entities and active catalog candidates. The adapter loads the latest snapshot, builds one if missing, performs conservative keyword/fuzzy matching, and returns structured `LeadClassifierResult` objects for every loaded message.

**Tech Stack:** Python 3.12, SQLAlchemy Core, existing classifier snapshot tables, existing lead runtime, pytest.

---

## Task 1: Snapshot Candidate Entries

**Files:**
- Modify: `src/pur_leads/services/classifier_snapshots.py`
- Test: `tests/test_classifier_snapshot_service.py`

- [x] Include `auto_pending`/`approved` catalog candidates in snapshots.
- [x] Add `candidate` and `candidate_term` entries.
- [x] Add candidate entries to the keyword index artifact.
- [x] Exclude rejected candidates.

## Task 2: Built-in Fuzzy Classifier

**Files:**
- Create: `src/pur_leads/integrations/leads/__init__.py`
- Create: `src/pur_leads/integrations/leads/fuzzy_classifier.py`
- Test: `tests/test_fuzzy_catalog_classifier.py`

- [x] Load the latest classifier snapshot or build one when missing.
- [x] Match terms from catalog and catalog candidates.
- [x] Distinguish `lead`, `maybe`, and `not_lead`.
- [x] Return valid lead match types compatible with `lead_matches`.

## Task 3: Worker Wiring

**Files:**
- Modify: `src/pur_leads/cli.py`
- Test: `tests/test_cli.py`

- [x] Wire the built-in classifier into the canonical worker registry.
- [x] Verify CLI worker classifies a queued message and creates a lead cluster.
- [x] Update no-message classify jobs to succeed with zero counts.

## Task 4: Verification And Rollout

- [x] Run focused classifier/runtime/CLI tests.
- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `node --check src/pur_leads/web/static/app.js`.
- [x] Run `TMPDIR=/home/admin/AI-AGENT/data/tmp/oleg-telegram-leads-pytest uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out` and report only line count.
- [ ] Commit and push to `main`.
- [ ] Deploy on `teamd-ams1`, restart web/worker, and verify `/health` plus `docker compose ps web worker`.
