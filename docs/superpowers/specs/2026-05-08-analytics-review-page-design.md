# Analytics Review Page Design

## Goal

Analytics stays a scanning surface. Each row gets one `Ревью` action that opens a
dedicated message review page. The review page is the operator workplace for:

- human lead verdict;
- review comment;
- detailed enrichment explanation;
- future text-selection constructor for dictionaries, facts, signals, and noise.

## Data Model

Add `message_reviews` as operator ground truth, separate from deterministic NLP
results.

Fields:

- `source_message_id`: Telegram source message id, primary key and foreign key
  target for the review state.
- `verdict`: one of `lead`, `not_lead`, `uncertain`, `noise`.
- `comment`: free-form operator note.
- `tags`: structured reason tags for later calibration.
- `created_at`, `updated_at`.

The NLP result remains immutable evidence for a particular enrichment job.
Operator review is mutable business feedback. The API exposes an effective lead
status on top of immutable NLP evidence: `lead` forces lead, `not_lead` and
`noise` force non-lead, and `uncertain` keeps the automatic verdict. Saving
`not_lead` or `noise` cancels unsent notification outbox rows for the same
source message.

## API

Extend Analytics API with review state:

- `GET /api/v1/analytics/messages/{message_id}` returns the existing live
  candidate plus `review`, `auto_is_lead`, `effective_is_lead`, and
  `lead_status_source`.
- `PUT /api/v1/analytics/messages/{message_id}/review` upserts verdict and
  comment.

The endpoint accepts `verdict: null` to clear the current verdict while keeping
or clearing the comment according to the payload.

## Frontend

Analytics table shows a single `Ревью` action for each message.

The route `#/analytics/review/{message_id}` opens a full page:

- source message metadata and text;
- enrichment-style evidence blocks already used by expanded Analytics rows;
- review panel with `Лид`, `Не лид`, `Сомнительно`, `Шум`;
- comment editor and save state;
- constructor panel placeholder.

The constructor is not implemented in the first increment, but its page area is
reserved so the next slice can add text selection without redesigning the route.

## Constructor Direction

The constructor will use selected text from the source message to create
configuration proposals, not immediate active config changes.

Proposal types:

- add alias to `vendors`, `devices`, `software`, `protocols`, or future
  `models`;
- create or update a fact phrase;
- create or update a domain signal phrase/dependency;
- create a noise signal.

Each proposal should preserve selected text, offsets, surrounding context, and
the target config reference. Applying a proposal should create a new
`nlp_config_revisions` row and allow preview/re-enrichment.

## Verification

- API tests for review upsert and readback.
- UI test that opens the review page, sets a verdict, writes a comment, and sees
  saved state.
- Regression check that Analytics still lists live candidates and Testing/manual
  enrichments do not create review rows.
