# Lead Traceability First Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first product-visible lead trace: from a lead card to the exact source message, matched catalog knowledge, decision record, raw ingest references, notification state, and feedback history.

**Architecture:** Start with a read-only trace assembler over existing SQLite tables, then expose it through `/api/leads/{cluster_id}/trace` and render it as a tab/panel inside the existing lead detail UI. This slice does not yet add the full generic `trace_events` / `trace_links` graph; it creates the operator-facing contract that the later graph will backfill.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, SQLite/Alembic, vanilla JS, existing Material Web/static CSS.

---

## Scope

This slice builds the first useful trace UI for operational leads. It must use the visual language already present on `/resources`: clean row lists, compact labels, low-card density, restrained dividers, and action-oriented sections.

Included:

- Read-only trace payload for one lead cluster.
- Source message and Telegram URL.
- Lead events and lead matches.
- Decision records linked to the cluster/event/message.
- Latest raw export reference when discoverable through `source_messages.archive_pointer_id`, `raw_metadata_json.raw_export`, or matching raw export run.
- Notification events linked to the cluster/event/message.
- Feedback history with learning effects.
- Lead detail UI section/tab for trace.
- Tests for auth, payload shape, and rendered page hook.

Deferred:

- Generic persisted `trace_events` / `trace_links` graph.
- Full trace bundle export.
- Prompt editor and AI-lab comparison UI.
- Source-agnostic Evidence workspace.
- Production reset execution; it is an operational deployment step after implementation.

## Files

- Create: `src/pur_leads/services/lead_trace.py`
- Modify: `src/pur_leads/web/routes_leads.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Modify: `tests/test_web_leads_routes.py`
- Modify: `tests/test_web_pages.py`
- Modify: `docs/README.md`
- Modify: `docs/operations/artifacts-and-production.md`

## Tasks

### Task 1: Trace API Contract

- [ ] Write failing test for `GET /api/leads/{cluster_id}/trace`.
- [ ] Verify it fails because the route does not exist.
- [ ] Implement `LeadTraceService` with existing domain tables only.
- [ ] Add API route and auth.
- [ ] Verify targeted test passes.

### Task 2: Lead Detail Trace UI

- [ ] Write failing page/static test for trace UI hook.
- [ ] Verify it fails before JS/HTML changes.
- [ ] Add trace button/section in the lead detail renderer.
- [ ] Add compact trace rows using existing Resources styling conventions.
- [ ] Verify targeted page/static tests pass.

### Task 3: Documentation And Operations Note

- [ ] Document that this is the first trace slice, not the final persisted trace graph.
- [ ] Document production reset policy: backup first, stop workers, preserve settings/admin/resources/secrets, delete domain data.
- [ ] Run markdown/diff checks.

### Task 4: Verification

- [ ] Run focused lead route tests.
- [ ] Run focused page/static tests.
- [ ] Run full pytest if the focused suite passes.
- [ ] Run ruff.
- [ ] Report exact verification output.
