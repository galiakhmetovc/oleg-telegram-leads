# Operator Guide Tab Design

Date: 2026-05-12

## Context

The current operator-facing help is split across:

- `frontend/src/settings/SettingsHelpPage.tsx` for technical config semantics
- `docs/operator-golden-rules.md` for lead/Golden workflow notes
- `ProjectDocumentationPage` for raw markdown browsing

This is not enough for the working mode we now have in production. The operator is
actively creating and refining lead coverage from real messages, moving between:

- `Analytics`
- `Testing`
- `Constructor`
- `Golden`
- `Settings`

At this point the system needs one canonical operator playbook that explains:

1. what the entities mean;
2. how to decide whether to create/update alias, fact, or signal;
3. how to test changes;
4. how to use Golden discipline;
5. how to avoid known failure modes.

The user explicitly wants this available as a separate tab in the web interface and
not hidden inside generic project docs.

## Goals

1. Add a dedicated top-level tab for a canonical operator guide.
2. Keep one authoritative source of content instead of duplicating the same rules in
   multiple UI surfaces.
3. Make the guide actionable: operator algorithm, decision rules, examples, and deep
   links into the product.
4. Keep `SettingsHelpPage` as concise technical reference, not as the full playbook.
5. Make the guide easy to update as the NLP model evolves.

## Non-Goals

1. Replacing existing `ProjectDocumentationPage`.
2. Turning the guide into a general architecture manual for developers.
3. Building a full interactive tutorial or wizard in the first pass.
4. Rewriting every inline help text in the application.

## User-Approved Direction

Approved direction:

- **Option A** from the browser mockup: one separate tab with one canonical guide.
- **Deep playbook**, not a short cheat sheet.

So the system should expose:

- a dedicated tab, recommended label: `Как работать`;
- one main operator guide page;
- one canonical markdown document behind that page;
- structured sections and a left-side table of contents;
- explicit links to `Testing`, `Golden`, `Settings`, `Analytics`, and `Constructor`.

## Approaches Considered

### Approach A: Dedicated Tab + Canonical Markdown + Guide Page

Add a new top-level tab and a dedicated `OperatorGuidePage` component that loads one
specific markdown file from project docs, renders it in a richer guide shell with:

- persistent local table of contents;
- quick links into app routes;
- anchor links for sections;
- compact operator-first framing above the markdown body.

Pros:

- one source of truth for content;
- separate from generic docs;
- easy to update without editing TSX prose blocks every time;
- keeps documentation and UI presentation loosely coupled.

Cons:

- requires a new page component and small routing work;
- requires markdown structure discipline.

### Approach B: Put Everything Into `SettingsHelpPage.tsx`

Extend the existing technical help page until it becomes the full playbook.

Pros:

- faster to wire initially;
- no new docs fetch path.

Cons:

- wrong boundary: technical reference and operator workflow become mixed;
- harder to maintain;
- less suitable for long structured content;
- harder to deep-link and scale.

### Approach C: Use Existing `ProjectDocumentationPage` Only

Write a big markdown document and tell operators to open it via the raw docs viewer.

Pros:

- minimal implementation.

Cons:

- not a dedicated workflow surface;
- navigation is too generic;
- does not match the user's request for a clear separate tab;
- too much friction for daily operator work.

## Recommendation

Use **Approach A**.

Concretely:

1. add a dedicated top-level tab `Как работать`;
2. add a new markdown document as the canonical source;
3. add an `OperatorGuidePage` component that fetches that markdown and renders it in a
   guide-first shell;
4. leave `SettingsHelpPage` in place as the compact technical semantics page;
5. leave `ProjectDocumentationPage` in place for developers and raw document browsing.

## Canonical Content Source

Create a new markdown file:

- `docs/how-to-work-in-system.md`

This becomes the single operator-facing canonical document.

Why not reuse `docs/operator-golden-rules.md` as-is:

- it is narrower than the new requirement;
- it is already focused on Golden and parts of the settings model;
- expanding it in place would blur its original intent and make the title misleading.

`docs/operator-golden-rules.md` can remain as legacy reference or later be merged into
the new guide after content migration, but the new tab should point at the new
canonical file.

## Page Structure

Recommended UI structure for the new page:

1. Header
   - title: `Как работать в системе`
   - short subtitle: what the page is for
   - quick actions row with links/buttons:
     - `Открыть Testing`
     - `Открыть Golden`
     - `Открыть Настройки`
     - `Открыть Аналитику`
     - `Открыть Конструктор`

2. Left sidebar
   - generated table of contents from markdown headings
   - sticky on desktop
   - collapsible on mobile

3. Main content pane
   - rendered markdown from `docs/how-to-work-in-system.md`
   - anchor links for sections
   - compact callout blocks for key invariants

4. Optional right-side utility block in future
   - current active section
   - “open related page” shortcuts
   - recent real examples

First version should use only header + left TOC + content pane.

## Guide Information Architecture

The guide should be written as a practical operator algorithm, not as abstract
architecture documentation.

Recommended section order:

1. `Что система считает лидом`
2. `Базовая модель: sentence, span, alias, fact, signal`
3. `Жесткие правила, которые нельзя нарушать`
4. `Алгоритм работы с новым сообщением`
5. `Когда создавать alias`
6. `Когда создавать fact`
7. `Когда обновлять signal`
8. `Как работать через Testing`
9. `Как работать через Golden`
10. `Как читать score, reasons, review lane`
11. `Как обновлять словари`
12. `Как обновлять facts`
13. `Как обновлять signals`
14. `Как обновлять scoring и review lanes`
15. `Как проверять, что ничего не сломалось`
16. `Типовые ошибки и anti-patterns`
17. `Разборы реальных lead-кейсов`
18. `Короткий чеклист оператора`

## Required Content Rules

The guide must explicitly preserve the working semantics already agreed in the repo:

1. `alias dictionary` is for named entities only.
2. `fact rule` is for semantic/intent/context/domain matching.
3. `signal` is derived only from facts.
4. dictionaries do **not** do lemmatized search.
5. exact and lemmatized matching belong to fact rules only.
6. one text fragment must have one owner.
7. long span wins over short overlapping span.
8. one matched alias may emit multiple derived facts.
9. `same_span` and `same_sentence` are support relations, not manual operator config.

These points must appear in operator language, not only in developer shorthand.

## What The Operator Algorithm Must Say

The main operator workflow should be written in explicit sequence:

1. Start from a real message:
   - from `Analytics`, or
   - by manual input in `Testing`, or
   - via `Constructor`.

2. Run current preview.

3. Inspect:
   - facts;
   - signals;
   - score;
   - review lane;
   - missing evidence.

4. Decide what kind of gap this is:
   - named entity gap -> alias dictionary;
   - semantic phrase gap -> fact rule;
   - business aggregation gap -> signal or review lane;
   - scoring issue -> weights / thresholds / lane conditions.

5. Update the smallest correct entity.

6. Re-run the same text in `Testing`.

7. Add or update a `Golden` example if the case matters.

8. Re-run relevant Golden examples.

9. Only keep the change if:
   - the target example is fixed;
   - old Golden examples did not regress;
   - the new rule is not overly generic.

## Real Examples

The guide must include real examples already established in the system, for example:

- intercom request with project context;
- apartment video surveillance request;
- Zigbee gateway / smart home request;
- Yandex smart home affecting electrical drawings;
- leak sensor shown on drawings;
- winter garden / climate control backup lead.

Each example should show:

1. original text;
2. what is alias;
3. what is fact;
4. what signal fires;
5. what lane it lands in;
6. what would be a common wrong modeling choice.

## Navigation Links

The guide page should contain direct route links into the app:

- `#/testing`
- `#/golden`
- `#/settings`
- `#/analytics`
- `#/constructor`

If the app currently uses numeric page state instead of explicit named hashes for all
tabs, implementation should still expose stable hash-based destinations for guide links,
or reuse existing route helpers where available.

The operator should be able to jump from a guide section directly into the relevant
workspace.

## UI Relationship With Existing Pages

### Keep

- `SettingsHelpPage.tsx` as a compact technical reference
- `ProjectDocumentationPage` as a raw repo docs browser

### Add

- `OperatorGuidePage.tsx`
- new top navigation tab `Как работать`

### Optional Small Changes

- from `SettingsHelpPage`, add a link like `Открыть полный операторский guide`
- from `ProjectDocumentationPage`, nothing special is required for first version

## Implementation Outline

### Frontend

1. Add new page component:
   - `frontend/src/operator-guide/OperatorGuidePage.tsx`

2. Add top nav tab in `App.tsx`:
   - recommended placement: after `Справка` and before `Проектная документация`, or
     immediately before `Справка`
   - recommendation: place `Как работать` before `Справка`, because the workflow
     playbook is more important than low-level technical semantics

3. Reuse document loading pattern from `ProjectDocumentationPage`:
   - fetch a single fixed document path
   - render via the existing markdown renderer pattern

4. Extract or reuse markdown rendering helper if needed, instead of duplicating logic
   from `RuntimePages.tsx`

5. Build a local table of contents from markdown headings

6. Add quick-link buttons to relevant app routes

### Documentation

1. Create `docs/how-to-work-in-system.md`
2. Move or rewrite the current operator rules into this file in operator language
3. Link to supporting docs where useful, but avoid making the operator bounce around
4. Update `docs/architecture.md` and `docs/decisions.md` to note:
   - canonical operator guide path;
   - separate guide tab;
   - split between workflow guide and technical help

## Testing Strategy

Minimum tests:

1. `App` navigation test:
   - new tab appears;
   - clicking it opens the guide page.

2. Guide page load test:
   - fetches the expected markdown file;
   - renders the guide title.

3. Quick links test:
   - route buttons point to the intended destinations.

4. TOC test:
   - headings from markdown appear in sidebar navigation.

5. Regression:
   - existing `SettingsHelpPage` and `ProjectDocumentationPage` tests keep passing.

## Risks

1. If content is duplicated between `SettingsHelpPage` and the new guide, they will drift.
   Mitigation: keep `SettingsHelpPage` short and point to the guide.

2. If guide links rely on unstable page indexes instead of explicit route helpers, links
   can break later.
   Mitigation: use stable hash routes or central navigation helpers.

3. If the guide becomes too theoretical, operators will ignore it.
   Mitigation: write it as workflow + decisions + real examples.

## Rollout

Phase 1:

- add tab;
- add canonical markdown;
- add guide page;
- add quick links and TOC;
- ship with the current lead-modeling practice.

Phase 2, only if needed:

- enrich guide with more screenshots or embedded examples;
- add page-level links from Settings and Golden back into specific sections.

## Result

After this change, the product should have:

1. one explicit operator workflow tab;
2. one canonical operator guide document;
3. a clear algorithm for deciding when to create or update alias, fact, signal, scoring,
   and Golden examples;
4. less ambiguity in day-to-day lead coverage work.
