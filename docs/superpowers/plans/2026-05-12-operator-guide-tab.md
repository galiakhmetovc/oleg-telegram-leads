# Operator Guide Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated operator playbook tab in the web UI, backed by one canonical markdown guide that explains how to work with aliases, facts, signals, Golden, Testing, Analytics, Constructor, and Settings.

**Architecture:** Reuse the existing project-docs API as the single document transport, keep the operator guide content in one markdown file under `docs/`, and add a focused React page that wraps the markdown with operator-first navigation, TOC, and quick links. Keep `SettingsHelpPage` as the technical reference and avoid duplicating semantics across multiple UI surfaces.

**Tech Stack:** React, Vite, TypeScript, MUI, Vitest, existing project-docs API and markdown preview rendering.

---

### Task 1: Lock The Frontend Contract With Failing Tests

**Files:**
- Modify: `frontend/src/App.test.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] Add a nav test that expects a top-level `Как работать` tab.
- [ ] Add a guide-page test that expects the app to fetch `docs/how-to-work-in-system.md` through the project-docs API and render the guide heading.
- [ ] Add assertions for operator quick links and the generated TOC on the guide page.
- [ ] Run the focused Vitest cases and confirm they fail for the expected missing-tab/missing-page reasons.

### Task 2: Add The Canonical Operator Guide Document

**Files:**
- Create: `docs/how-to-work-in-system.md`
- Modify: `docs/operator-golden-rules.md`

- [ ] Write the full operator algorithm as one canonical markdown document in Russian.
- [ ] Include the agreed invariants: alias dictionary vs fact rule vs signal, no lemmatized search in dictionaries, one owner per span, long span beats short span, derived facts from one matched alias, and `same_span`/`same_sentence` as support relations.
- [ ] Include practical workflows for `Testing`, `Golden`, `Settings`, `Analytics`, and `Constructor`.
- [ ] Include real lead examples already used in the system so the guide is grounded in production practice.
- [ ] Add a short pointer in `docs/operator-golden-rules.md` to the new canonical guide instead of trying to duplicate the full playbook there.

### Task 3: Implement The Guide Page And Routing

**Files:**
- Create: `frontend/src/operator-guide/OperatorGuidePage.tsx`
- Modify: `frontend/src/runtime/RuntimePages.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Add a reusable markdown-preview export or shared helper so the new page can render the canonical markdown without duplicating the renderer logic.
- [ ] Implement `OperatorGuidePage` with a header, operator quick links, a left TOC derived from markdown headings, and the main markdown body.
- [ ] Add a stable hash route for the page and wire it into `App.tsx`.
- [ ] Add a new top-level tab `Как работать` without disturbing existing hidden/direct routes such as `#/configurator`.
- [ ] Add focused styles that match the existing operator shell: sticky TOC on desktop, compact mobile stacking, restrained surfaces, and no extra card clutter.

### Task 4: Align Existing Help And Architecture Docs

**Files:**
- Modify: `frontend/src/settings/SettingsHelpPage.tsx`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`

- [ ] Add a clear handoff from technical `Справка` to the full operator guide.
- [ ] Document that `Как работать` is now the canonical operator playbook tab.
- [ ] Record the decision to keep one authoritative markdown guide and a separate technical reference surface.

### Task 5: Verify The Full Flow

**Files:**
- Test: `frontend/src/App.test.tsx`

- [ ] Run the focused guide tests and confirm the new behavior passes.
- [ ] Run the full frontend test suite.
- [ ] Run the frontend build.
- [ ] Run `git diff --check`.
- [ ] Re-read the original spec `docs/superpowers/specs/2026-05-12-operator-guide-tab-design.md` and verify the implementation matches the approved scope before claiming completion.
