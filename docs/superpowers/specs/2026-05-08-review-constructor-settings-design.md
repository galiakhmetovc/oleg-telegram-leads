# Review Constructor Settings Design

## Goal

The Review page must let an operator turn selected source-text fragments into
active NLP settings without leaving the review workflow.

## Scope

Implemented constructor actions:

- `В словарь`: add selected text as an alias to an existing or new catalog item
  in `vendors`, `protocols`, `devices`, or `software`.
- `В факт`: add selected text to an existing or new fact rule as either an exact
  phrase or a backend-built lemmatized phrase.
- `В доменный сигнал`: add selected text to an existing or new signal rule as an
  exact or lemmatized phrase. Newly created signals get a `0` scoring weight so
  they do not change lead score until the operator explicitly tunes scoring.
- `В шум`: existing fast path to `operator_noise`.

All changes write a new active PostgreSQL `nlp_config_revisions` row. YAML files
remain bootstrap defaults only.

## API

Add three settings constructor endpoints under `/api/v1/settings/nlp/constructor`:

- `POST /alias`
- `POST /fact`
- `POST /signal`

Each endpoint receives selected `text`, optional `source_message_id`, target
metadata, validates the resulting NLP config, saves a new revision, and returns
the updated NLP snapshot plus a settings deeplink target.

## UI

The Review constructor buttons open compact MUI dialogs:

- alias dialog: catalog, existing/new mode, key, canonical, type, fact types;
- fact dialog: existing/new mode, rule type, label, group, match mode;
- signal dialog: existing/new mode, rule type, label, group, match mode.

Dialogs are prefilled from selected text. Successful saves show the affected
setting and update the frontend settings cache from the backend response.

## Error Handling

Empty selected text, empty keys, missing fact types, invalid semantic phrases,
and invalid resulting NLP config return `422` from the backend and render as
operator-visible errors in the Review constructor panel.

## Verification

- API tests verify alias, fact, and signal constructors write PostgreSQL
  revisions rather than YAML files.
- UI tests verify selected text opens dialogs and sends the expected API
  payloads.
- Full backend tests, ruff, mypy, frontend tests/build, Docker Compose config,
  and diff whitespace checks are required before completion.
