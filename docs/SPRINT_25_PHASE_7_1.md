# Sprint 25 Phase 7.1 — Best Bets evidence score hotfix

This hotfix corrects issues exposed by the first correlation-aware card deployment.

## Fixes

- Rebuilds the display score from raw evidence rather than inheriting a prior capped score.
- Applies explicit penalties when model probability or recent evidence is unavailable.
- Adds a final canonical deduplication pass before exposure caps and ranking.
- Ensures card rank numbers are assigned only after the final list is constructed.
- Makes the evidence patch replaceable in generated HTML so later fixes update existing dashboards.

## Guardrails

- No model projections, sportsbook lines, probabilities, or production recommendations are changed.
- This is a dashboard scoring and shortlist construction fix only.
