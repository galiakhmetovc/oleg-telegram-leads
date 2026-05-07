# Current State

## Active Work

- Build PUR Leads v2 from a clean scaffold.
- Keep v1 only as reference material.
- Use exported production-confirmed lead messages as seed examples for later design.
- Follow root `AGENTS.md` as the project working rules.
- First product slice: web text enrichment UI with FastAPI snapshots, SSE
  progress, Celery worker execution, PostgreSQL persistence, and configurable
  Natasha/Yargy NLP pipeline.
- Current dev UI is exposed through host Caddy at
  `https://secclaw.qlbc.ru:19443/`; `/api/*` and SSE are proxied to FastAPI.
- Default NLP config now recognizes the smart-home automation lead case with
  customer intent, vendor, solution area, and electrical design context signals.
- Default NLP config also recognizes hot Zigbee installation requests with
  provider search, service location, automation components, and controlled devices.

## Blockers

- Product flows for v2 are not specified yet.
- Host disk pressure is high: after clearing npm/uv caches, `/` still had about
  2.3 GB free and 98% usage on 2026-05-07.

## Next Steps

1. Review the first enrichment UI through Caddy.
2. Specify the next product flow after arbitrary text enrichment.
3. Keep an eye on host disk usage before larger dependency/model downloads.
