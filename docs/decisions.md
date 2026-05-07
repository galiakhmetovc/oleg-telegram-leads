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
