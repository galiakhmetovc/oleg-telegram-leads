# Configurator UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visual Configurator page for navigating and editing dictionaries, facts, signals, and lead scoring through their dependencies.

**Architecture:** Build a frontend-only feature over the existing settings API. A focused `configurator` module derives a navigation/entity/dependency view from `SettingsSnapshot`, edits a small selected subset, and persists the full NLP config through the current `PUT /api/v1/settings/nlp` endpoint.

**Tech Stack:** React, TypeScript, MUI, Vite/Vitest, existing FastAPI settings API.

---

### Task 1: Build Configurator Model And Component

**Files:**
- Create: `frontend/src/configurator/ConfiguratorPage.tsx`
- Test: `frontend/src/configurator/ConfiguratorPage.test.tsx`

- [x] Write a failing component test that renders a sample settings snapshot, shows domain/layer navigation, selects a domain, and displays dependent facts/signals.
- [x] Implement derived domain/layer/entity model helpers inside `ConfiguratorPage.tsx`.
- [x] Render the three-column workspace: navigator, entity card, dependency inspector.
- [x] Add simple editing for selected aliases/rules and save through `PUT /api/v1/settings/nlp`.
- [x] Run `npm test -- ConfiguratorPage.test.tsx`.

### Task 2: Wire Configurator Into App Shell

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [x] Add `Конфигуратор` top-level tab and `#/configurator` hash routing.
- [x] Pass shared settings snapshot, load state, and update callback into `ConfiguratorPage`.
- [x] Add a lightweight App test that opens the Configurator tab.
- [x] Run targeted frontend tests.

### Task 3: Documentation And Verification

**Files:**
- Modify: `state/current.md`

- [x] Document the first Configurator slice and its limits.
- [x] Run `npm run build`.
- [x] Run `npm test`.
- [x] Commit the implementation.
