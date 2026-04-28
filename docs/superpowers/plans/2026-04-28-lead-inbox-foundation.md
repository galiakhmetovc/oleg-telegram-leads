# Lead Inbox Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SQLite and service foundation for auditable lead detection events, cluster-based Leads Inbox work items, match evidence, feedback, and runtime classification hooks.

**Architecture:** Keep detection facts immutable in `lead_events`/`lead_matches`; keep human workflow state in `lead_clusters`; keep corrections in `feedback_events`. First implementation uses deterministic fake classifiers in tests and adapter interfaces for real AI/keyword classifiers later.

**Tech Stack:** Python 3.12, SQLAlchemy Core, Alembic, SQLite, pytest, existing Telegram/source/catalog/runtime foundation.

---

## Scope

This plan implements backend storage and deterministic services for lead inbox foundations. It does not implement web UI screens, Telegram notifications, CRM conversion records, or real AI classification.

## Task 1: Lead Inbox Schema

- [x] Implement migration/model tables and verify constraints/identity tests.

**Files:**
- Create: `migrations/versions/0004_lead_inbox_foundation.py`
- Create: `src/pur_leads/models/leads.py`
- Test: `tests/test_lead_inbox_migration.py`

- [ ] Add `lead_events`, `lead_clusters`, `lead_cluster_members`, `lead_cluster_actions`, `lead_matches`, `feedback_events`, `crm_conversion_candidates`, and `crm_conversion_actions`.
- [ ] Add unique index on `(source_message_id, classifier_version_id, detection_mode)`.
- [ ] Add SQL-visible fields for cluster queue filtering: status, review status, source, category, confidence, retro flag, notification timestamps.
- [ ] Verify constraints reject invalid decisions/statuses and unique event identity works.

## Task 2: Lead Event Recording And Match Evidence

- [x] Implement lead event/match recording and verify dedupe/evidence tests.

**Files:**
- Create: `src/pur_leads/repositories/leads.py`
- Create: `src/pur_leads/services/leads.py`
- Test: `tests/test_lead_event_service.py`

- [ ] Record lead events from `source_messages` plus classifier result DTO.
- [ ] Store lead matches pointing to classifier snapshot entries/catalog terms/items/offers/categories.
- [ ] Preserve status/weight snapshots from classifier entries at detection time.
- [ ] Deduplicate by source message/classifier version/detection mode without mutating old decisions.

## Task 3: Cluster Creation And Auto-Merge

**Files:**
- Modify: `src/pur_leads/services/leads.py`
- Test: `tests/test_lead_cluster_service.py`

- [ ] Create one `lead_cluster` per actionable event when no compatible cluster exists.
- [ ] Auto-merge by same monitored source + sender + category inside configurable time window.
- [ ] Add cluster members with roles `primary`, `trigger`, `context`, or `clarification`.
- [ ] Update cluster counters, confidence/value/negative score aggregates, first/last message times.
- [ ] Store auto-merge action rows with reason and score.

## Task 4: Feedback And Inbox Actions

**Files:**
- Modify: `src/pur_leads/services/leads.py`
- Test: `tests/test_lead_feedback_service.py`

- [ ] Record feedback events against cluster/event/match/message/term targets.
- [ ] Enforce `not_lead` requires a reason code.
- [ ] Implement `lead_confirmed`, `not_lead`, `maybe`, `snooze`, `duplicate`, and `mark_context_only` cluster actions.
- [ ] Distinguish classifier feedback from commercial outcomes through `feedback_scope` and `learning_effect`.

## Task 5: Leads Inbox Query Service

**Files:**
- Create: `src/pur_leads/services/lead_inbox.py`
- Test: `tests/test_lead_inbox_service.py`

- [ ] Return cluster queue rows with primary message, status, confidence, category, matched terms/items, retro/maybe/auto_pending flags, event count, and feedback count.
- [ ] Support filters for status, source, category, retro, maybe, and minimum confidence.
- [ ] Return detail payload with cluster timeline, events, matches, and feedback.

## Task 6: Runtime Classification Handler

**Files:**
- Modify: `src/pur_leads/workers/runtime.py`
- Test: `tests/test_lead_runtime_handlers.py`

- [ ] Add adapter DTOs and handler registry for `classify_message_batch`.
- [ ] Handler reads unclassified/queued `source_messages`, calls injected classifier adapter, records events/matches/clusters, and marks messages classified.
- [ ] Missing classifier adapter fails visibly through existing scheduler event path.
- [ ] Tests use fake classifier only.

## Acceptance

Run:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src
docker compose config
```
