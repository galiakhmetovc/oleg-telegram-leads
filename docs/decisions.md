# Decisions

## 2026-05-07: Fresh v2 Codebase

PUR Leads v1 is historical reference only. V2 starts from a clean scaffold rather
than extending the old source tree.

## 2026-05-07: Core Stack

Use PostgreSQL, FastAPI, React, and Docker Compose as the base stack.

Rationale:

- PostgreSQL is the production database from day one.
- FastAPI gives a small, typed Python API surface.
- React + Vite + TypeScript gives a focused frontend toolchain.
- Docker Compose keeps local service wiring explicit and reproducible.

## 2026-05-07: Project Working Rules

Use root `AGENTS.md` as the mandatory working rules file for PUR Leads v2.

Rationale:

- Chat history is not a durable source of truth.
- Future agent sessions need one predictable place for project rules.
- Process rules, architecture rules, verification rules, and Definition of Done
  should be versioned with the project.

## 2026-05-07: Dev Containers Do Not Bake Source

In development mode, Docker images provide runtime tools and dependency layers only.
Backend and frontend source code is mounted from the host through bind volumes.

Rationale:

- The project is currently in active local development.
- Source changes should be visible without rebuilding images.
- Production image design is a separate future decision.

## 2026-05-07: Architecture Principles

Build v2 around Hexagonal Architecture / Ports and Adapters with explicit use
cases, domain boundaries, dependency inversion, repositories as ports, and clear
separation between API schemas, domain objects, DB models, and frontend types.

Apply GRASP, SOLID, DDD tactical patterns where useful, Dependency Injection,
Repository + Unit of Work, and testability by design.

Rationale:

- PUR Leads will contain substantial business behavior around Telegram data,
  lead review, NLP classification, evals, and operator workflows.
- Keeping framework and infrastructure dependencies outside the domain makes the
  system easier to test and change.
- Adult boundaries are cheaper to establish now than retrofit later.

## 2026-05-07: Frontend Product Direction

Build a working operator interface, not a landing page. Use Google Material
Design through MUI for the React UI.

Rationale:

- The product is an operational tool.
- Operators need dense, predictable screens: tables, filters, lists, forms,
  statuses, and review flows.
- Marketing-style hero sections and decorative UI do not serve the workflow.

## 2026-05-07: Verification Policy

All behavior-affecting changes are business logic and must be verified with a
method appropriate to risk. Tests are valuable when they protect real behavior;
do not write tests only for coverage theater.

Rationale:

- Backend, frontend, migrations, imports, classification, UI flow, and Docker
  wiring can all affect user-visible behavior.
- Verification may be unit, integration, API, UI smoke, manual, or another
  reproducible check depending on the change.

## 2026-05-07: Production-Derived Data

Production lead exports may be committed when they are useful for development,
evals, or regressions. Before committing production-derived data, explicitly
inspect what is being added and avoid accidental large dumps, secrets, tokens, or
irrelevant sensitive data.

Use `artifacts/` for local temporary exports and `datasets/` for small
versioned datasets when data should live in git.

Rationale:

- Real lead examples are important for NLP/eval quality.
- Data should be intentionally curated when it becomes part of the repository.
