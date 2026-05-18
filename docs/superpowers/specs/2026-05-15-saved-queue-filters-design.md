# Saved Queue Filters Design

## Goal

Add a local catalog of saved queue filters for `Рабочее место -> Очередь`.
Operators should be able to save the current queue state as a named filter,
apply it later, edit/delete it, and choose one saved filter as the default view.

Initial persistence is browser-local `localStorage`. There is no backend storage,
role model, or cross-device synchronization in this pass.

## Scope

The saved filter captures what messages are shown, not the table layout.

Included:
- advanced queue filters from `CandidateFilters`;
- MUI DataGrid column filters from `CandidateGridQueryState.columnFilters`;
- DataGrid quick search from `CandidateGridQueryState.quickFilter`;
- DataGrid sorting from `CandidateGridQueryState.sort`;
- preset metadata: id, name, default flag, created/updated timestamps.

Excluded for now:
- column visibility/order/width;
- backend persistence;
- sharing presets between browsers/users;
- permissions or owner model.

## Data Model

```ts
type CandidateQueueSavedFilter = {
  id: string;
  name: string;
  filters: CandidateFilters;
  gridState: CandidateGridQueryState;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
};
```

Storage key:

```ts
pur-leads.analytics.saved-filters.v1
```

The loader normalizes unknown/missing fields and ignores malformed records.
Only one saved filter may have `isDefault: true`; setting a new default clears
the previous one.

## Default Behavior

When the queue opens:
- if the current URL contains explicit queue filter/query params, the URL wins;
- otherwise, apply the local default saved filter if one exists;
- otherwise, use the system default: last 24 hours plus `reviewStatus=unreviewed`.

Deleting the current default removes the custom default and falls back to the
system default unless the operator marks another saved filter as default.

## UI

Add a compact saved-filter control to the candidate queue toolbar area, near
the period quick filters:

- select/menu: current saved filter or `Без сохраненного фильтра`;
- `Сохранить текущий`: opens a short dialog with name and `Сделать по умолчанию`;
- `Управлять`: opens a dialog with saved filters list.

Management dialog actions:
- apply;
- rename;
- update from current queue state;
- set/unset default;
- delete.

Applying a saved filter:
- replaces current `CandidateFilters`;
- replaces current `CandidateGridQueryState`;
- resets pagination offset to 0;
- updates the route hash using existing `analyticsListHash`.

Saving current state:
- stores the current filters/grid state exactly as active now;
- stores relative period as concrete filter values for this first pass.

## User Example

Preset: `Холодные LLM lead за неделю`

State:
- `receivedFrom`: seven days ago;
- `receivedTo`: empty;
- `temperature`: `cold`;
- `llmVerdict`: `lead`;
- `reviewStatus`: likely `unreviewed`;
- `sort`: optional, commonly `receivedAt desc`.

The operator can mark it as default, so opening the queue without URL filters
immediately shows that slice.

## Testing

Frontend tests should cover:
- saved filters persist to `localStorage`;
- default saved filter applies only when URL has no explicit filters;
- URL filters override local default;
- applying a saved filter updates API query params;
- saving current state captures advanced filters, grid filters, quick search,
  and sorting;
- deleting the default falls back to the system default.

No backend tests are required because persistence is local.
