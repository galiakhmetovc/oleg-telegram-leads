# Material Web Auth And Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the login, forced password change, and onboarding screens onto Material Web with a local asset build and minimal layout-only CSS.

**Architecture:** Use `@material/web` as the single UI component system for this UI slice. Build a local ESM bundle from npm into `src/pur_leads/web/static/vendor/material-web.js`, load it from FastAPI static assets, and keep `app.css` responsible for page layout and product-specific spacing only.

**Tech Stack:** FastAPI server-rendered HTML, vanilla JS, Material Web web components, npm/esbuild asset build, pytest, Playwright smoke checks.

---

### Task 1: Asset Pipeline

**Files:**
- Create: `package.json`
- Create: `package-lock.json`
- Create: `src/pur_leads/web/assets/material-web.js`
- Create: `src/pur_leads/web/static/vendor/material-web.js`
- Modify: `Dockerfile`
- Test: `tests/test_web_pages.py`

- [x] Write failing tests proving the page loads a local `/static/vendor/material-web.js` module and package metadata pins `@material/web`.
- [x] Add npm scripts and pinned dependencies.
- [x] Build the Material Web bundle locally.
- [x] Update Docker to run the asset build before Python packaging.

### Task 2: Material Auth Screens

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [x] Write failing tests for Material Web auth components.
- [x] Replace login/password-change inputs and buttons with Material Web fields and buttons.
- [x] Add JS helpers that read values from form-associated Material components.
- [x] Keep the existing local auth and forced password-change behavior.

### Task 3: Material Onboarding Screen

**Files:**
- Modify: `src/pur_leads/web/routes_pages.py`
- Modify: `src/pur_leads/web/static/app.js`
- Modify: `src/pur_leads/web/static/app.css`
- Test: `tests/test_web_pages.py`

- [x] Write failing tests for Material Web onboarding controls.
- [x] Replace onboarding buttons, text fields, and checkboxes with Material Web components.
- [x] Rework onboarding layout as a restrained Material 3 operational wizard.
- [x] Keep source onboarding as a link to the existing Sources section.

### Task 4: Verification And Deploy

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-28-pur-catalog-source-of-truth-design.md`

- [x] Document the Material Web decision and asset build.
- [x] Run npm build, `ruff`, JS syntax check, focused pytest, full pytest, and Playwright smoke.
- [ ] Commit, push, deploy, and verify server health plus `/onboarding` redirect.
