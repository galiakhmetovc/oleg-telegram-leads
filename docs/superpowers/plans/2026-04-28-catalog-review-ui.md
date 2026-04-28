# Catalog Review UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the administrator review automatically extracted catalog candidates in the web interface and promote approved item candidates into the operational catalog.

**Architecture:** Add a thin authenticated web/API layer over the existing catalog candidate and promotion services. Keep Telegram for urgent notifications only; catalog review stays in the web CRM/admin surface.

**Tech Stack:** FastAPI, existing cookie admin auth, vanilla JS/CSS, SQLite-backed catalog repositories, pytest.

---

## Scope

This layer is for human review of extracted facts. It does not replace the later AI extractor, evidence drill-down UI, vector search, or multi-role permission model.

## Task 1: Candidate Review API

**Files:**
- Create: `src/pur_leads/web/routes_catalog.py`
- Modify: `src/pur_leads/web/app.py`
- Modify: `src/pur_leads/services/catalog_candidates.py`
- Modify: `src/pur_leads/repositories/catalog_candidates.py`
- Test: `tests/test_web_catalog_routes.py`

- [x] Add authenticated candidate listing with status/type filters.
- [x] Add authenticated review endpoint for approve/reject/needs_review/mute.
- [x] Promote approved item/phrase candidates through the existing catalog service.
- [x] Audit every review action.
- [x] Cover unauthorized access, approval promotion, and rejection without promotion.

## Task 2: Web Catalog Page

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [x] Add protected `/catalog` page and navigation.
- [x] Render candidate queue, filters, selected candidate detail, raw payload, terms, and review controls.
- [x] Keep the UI consistent with the existing operational workspace.
- [x] Cover page protection and shell rendering.

## Task 3: Extraction Quality Patch

**Files:**
- Modify: `src/pur_leads/integrations/catalog/heuristic_extractor.py`
- Test: `tests/test_heuristic_catalog_extractor.py`

- [x] Split PDF text where technical markers were joined to service names.
- [x] Classify safety/security notification services as `security_alarm`.
- [x] Cover the joined-marker regression.

## Task 4: Verification And Rollout

- [x] Run `uv run --extra dev ruff check`.
- [x] Run `uv run --extra dev ruff format --check`.
- [x] Run `uv run --extra dev mypy src`.
- [x] Run `uv run --extra dev pytest -q`.
- [x] Run `docker compose config >/tmp/oleg-telegram-leads-compose.out` and report only line count.
- [ ] Commit and push to `main`.
- [ ] Deploy on `teamd-ams1`, restart web/worker, and verify `/health` plus `docker compose ps web worker`.
- [ ] Rebuild server-side extracted candidates with the improved heuristic extractor.
