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
- Settings rule editing now presents operator-facing matching modes: exact
  phrases and lemmatized phrases. Exact/semantic rules are edited with explicit
  add/edit/delete actions. New lemmatized phrases are built by the backend from
  operator-entered text and preserve `source_text` alongside generated lemmas.
- A Help tab in the web UI explains exact versus lemmatized matching and when to
  use each mode.
- Settings Center now also exposes editable alias catalogs for `vendors`,
  `protocols`, `devices`, and `software`. These catalogs keep canonical names,
  Latin/Cyrillic/transliterated/mistyped aliases, alias type, and links to
  semantic signal/fact types.
- Default NLP config includes a broad curated first pass for РФ/СНГ smart-home
  market terms: Яндекс/Сбер/Aqara/Xiaomi/Tuya/Sonoff/Rubetek/Livicom/Wiren Board,
  leak protection brands, CCTV/access vendors, Matter/Zigbee/Z-Wave/KNX/Wi-Fi/
  BLE/Modbus/MQTT/PoE protocols, common devices, and smart-home software such as
  Алиса, Home Assistant, Apple Home/HomeKit, Google Home, Smart Life, Aqara Home,
  Mi Home, eWeLink, Zigbee2MQTT, Node-RED, ioBroker, MajorDoMo, and video apps.
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
- Default NLP config recognizes value-evaluation smart-home leads where customers
  ask whether they need a smart home, who it is for, what benefits it gives, and
  mention family apartment context, budget constraints, climate, or lighting
  scenarios.
- Default NLP config recognizes the latest follow-up PUR lead examples: child
  room smart speaker/audio wiring as a warm lead, leak sensor power/output
  questions, commercial intercom/access-control recovery, white-box smart-home
  design planning, security technical projects with video/access/alarm systems,
  nanny camera contractor search, and Wi-Fi electric curtain control.
- Default NLP config recognizes the latest motion-lighting, Zigbee/Yandex relay,
  and HVAC/design leads: timed night lighting by motion sensor with independent
  wall-light control, smart relay modules for lights/tracks connected to Alice,
  and O'Climate/Orac static-pressure chambers for channel air conditioning
  without misclassifying them as video surveillance.
- Default NLP config recognizes Neptun/Нептун water leak monitoring leads,
  including the typo `Нептуп`, ProW/Profi product mentions, wired leak sensors,
  sensor-trigger monitoring, and smartphone information output.
- Dev PostgreSQL active NLP config was refreshed to revision 19. The `need`
  signal no longer stores Russian forms such as `нужно`, `нужна`, `нужен` as
  exact phrases; they are represented as lemmatized phrase rules with preserved
  operator source text. Revision 16 also includes the Neptun water leak
  monitoring lead calibration, and revision 19 includes the smart-home alias
  catalogs plus calibrated semantic signal/fact weights.
- `RussianTextEnricher` now precompiles Yargy parsers once per enricher
  instance and shares one Yargy `MorphTokenizer` across compiled rules instead
  of creating a separate `pymorphy2` analyzer for every parser. This keeps
  default-config rule tests around hundreds of MB instead of multi-GB RSS. A
  local batch CLI can write full enrichment JSONL for exported messages without
  creating API/Celery jobs per message.
- Benchmark on the first 300 designer-channel messages with full enrichment:
  300 processed, 0 failed, 6 leads, 65.31 seconds, 4.59 messages/sec, peak RSS
  about 1.34 GB, output 1.9 MB. Linear estimate for 528953 messages on one
  process is about 32 hours and about 3.24 GiB JSONL output.
- Agent verification should avoid Caddy smoke checks unless explicitly requested;
  use backend tests and direct service/container checks by default.
- Backend `uv run pytest -q` skips slow full-Natasha NLP smoke tests by default.
  Run them explicitly with `uv run pytest --runslow ...` when validating the
  full morph/syntax/NER path.

## Blockers

- Product flows for v2 are not specified yet.
- Host disk pressure is high: after clearing npm/uv caches, `/` still had about
  2.3 GB free and 98% usage on 2026-05-07.

## Next Steps

1. Review the lead assessment UI manually in the browser.
2. Start curating a versioned eval dataset of positive leads, non-leads, and
   borderline cases.
3. Keep an eye on host disk usage before larger dependency/model downloads.
