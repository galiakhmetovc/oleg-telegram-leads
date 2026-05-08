# Review Lanes And Confirmed Leads Plan

## Goal

Make the analytics screen useful for the broad batch result by separating
candidates into review lanes and keeping the lane logic configurable.

## Steps

1. Add a generic review-lane matcher over existing candidate fields: score,
   temperature, reasons, domain signals, facts, solution areas, customer
   segments, intent signals, and noise signals.
2. Store lane definitions in `lead_scoring.review_lanes` so they are part of the
   PostgreSQL-backed NLP config revision and not hardcoded in Python.
3. Persist the assigned lane on `analytics_candidates`, precompute lane
   aggregates, and expose lane filtering through the analytics API.
4. Show review lanes in the analytics UI and let the operator filter candidates
   by lane from a select populated by aggregates.
5. Keep the 9 confirmed production leads as local analysis evidence for now.
   Promote them to a committed golden/eval dataset only after explicit data
   review.
