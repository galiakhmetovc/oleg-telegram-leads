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
- Default NLP config recognizes apartment video surveillance requests with
  provider search, consultation need, camera, wall mounting, and wiring outputs.
- Settings Center is available in the UI. NLP/domain settings are viewed,
  previewed, and saved as active PostgreSQL revisions; YAML files are bootstrap
  defaults only. Runtime/env settings are shown read-only.
- Default NLP config recognizes the confirmed artifact lead about hiding a leak
  sensor in porcelain stoneware and documenting the solution on drawings/schemes.
- Enrichment results include `lead_assessment`: deterministic PUR lead verdict,
  score, temperature, solution areas, customer segments, reasons, and noise
  signals. Lead scoring thresholds, weights, and mappings are editable in the
  Settings Center and stored in PostgreSQL config revisions.
- Default NLP config recognizes the developer-provided smart-home apartment
  modification lead: apartments with smart home from a developer, socket/switch
  changes, electrical scheme changes, and warranty risk.
- Default NLP config recognizes early research/design leads where the author asks
  which useful smart-home systems to implement in a project and where to study
  the topic.
- Dev PostgreSQL active NLP config was refreshed to revision 8 from the current
  bootstrap config so worker jobs use the new PUR scoring settings.

## Blockers

- Product flows for v2 are not specified yet.
- Host disk pressure is high: after clearing npm/uv caches, `/` still had about
  2.3 GB free and 98% usage on 2026-05-07.

## Next Steps

1. Review the lead assessment UI through Caddy.
2. Start curating a versioned eval dataset of positive leads, non-leads, and
   borderline cases.
3. Keep an eye on host disk usage before larger dependency/model downloads.
