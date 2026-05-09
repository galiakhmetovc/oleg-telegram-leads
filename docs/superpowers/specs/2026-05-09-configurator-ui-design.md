# Configurator UI Design

## Goal

Add an operator-facing Configurator page for editing NLP configuration through the causal model:

```text
dictionaries -> facts -> domain signals -> lead assessment
```

The existing Settings Center remains the advanced editor. The Configurator is the primary
workspace for understanding and safely editing a selected rule, alias, or scoring item.

## First Slice

- Add a top-level `Конфигуратор` page.
- Load the existing `SettingsSnapshot`; do not introduce a new backend storage model.
- Show a left navigation tree with:
  - domain groups from signal/fact `group` values;
  - layers: dictionaries, facts, signals, lead scoring.
- Show a central entity card for the current selection:
  - domain overview for a group;
  - editable alias card for dictionary items;
  - editable rule card for facts/signals;
  - scoring overview for weights, solution areas, customer segments, review lanes, and caps.
- Show a right dependency inspector:
  - alias emitted facts and signals that depend on its identity fact;
  - rule fact dependencies;
  - signal weights and lead-scoring usage;
  - facts/signals used by solution areas, segments, lanes, and caps.
- Save NLP changes through the existing `PUT /api/v1/settings/nlp` endpoint and update the shared settings snapshot.

## Non-Goals For This Slice

- No new graph visualization dependency.
- No batch/golden diff endpoint yet.
- No full CRUD replacement for every Settings Center editor.
- No backend schema changes.

## UX Shape

The page is a dense operational workspace:

- left: tree-like navigator;
- center: selected entity and editable fields;
- right: dependency/impact inspector.

Operators should be able to answer:

- what this entity is;
- how it matches text;
- what facts/signals it emits or depends on;
- how it affects lead score and routing;
- where to continue detailed editing if the simple card is not enough.
