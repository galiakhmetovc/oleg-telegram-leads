# Smart-Home Alias Catalogs Plan

**Goal:** Improve PUR lead detection by separating semantic domain signals from
market spellings for smart-home platforms, protocols, devices, software, models,
and common РФ/СНГ brand aliases.

## Scope

- Keep semantic signal categories stable: smart-home platforms, protocol/gateway
  mentions, leak protection, lighting automation, climate automation, access
  control, intercom, video surveillance, power backup, and related areas.
- Add separate editable alias catalogs in the NLP config revision:
  `vendors`, `protocols`, `devices`, and `software`.
- For each alias entry store canonical name, alias type, written variants, and
  linked signal/fact types.
- Expose these catalogs through Settings API and Settings Center.
- Seed a broad curated first pass based on current official/company sources and
  frequent РФ/СНГ smart-home terminology.

## Checklist

- [x] Add failing config, pipeline, API, and UI tests for alias catalogs.
- [x] Extend NLP config loader and `RussianTextEnricher` with precompiled alias
  matching.
- [x] Add Settings API serialization/deserialization for alias catalogs.
- [x] Add Settings Center UI section for viewing/editing alias catalogs.
- [x] Add bootstrap YAML catalogs for vendors, protocols, devices, and software.
- [x] Add scoring support for new semantic signal/fact types.
- [x] Update architecture, decisions, and current state docs.
- [x] Refresh active PostgreSQL NLP config revision.
- [x] Run verification and commit.

## Verification Notes

- The first verification attempt exposed a memory issue: each compiled Yargy
  parser created its own default `MorphTokenizer`/`pymorphy2` analyzer, so the
  broad default config could push a single pytest process into multi-GB RSS.
- `RussianTextEnricher` now shares one Yargy `MorphTokenizer` across compiled
  signal, fact, and alias parsers. Backend `uv run pytest -q` runs safely by
  default and skips only the explicit slow full-Natasha smoke test.
