# Sprint 23 Phase 4 — Shadow Tracking and Validation

Phase 4 creates a forward-validation record for the Sprint 23 player-prop models without changing production recommendations.

## Workflow

`WNBA Sprint 23 Phase 4 Shadow Validation`

The workflow can be run manually and is scheduled twice daily. Each run:

1. Rebuilds the current DraftKings and FanDuel shadow opportunities.
2. Appends a timestamped market snapshot to the permanent ledger.
3. Finds completed games in the verified player-game warehouse.
4. Grades each opening shadow entry as win, loss, push, or pending.
5. Calculates hypothetical profit from a flat $1 stake.
6. Measures line CLV and price-implied-probability movement.
7. Summarizes hit rate, ROI, model EV, and CLV by stat, book, and side.
8. Runs QA and commits the validation artifacts.

## Artifacts

- `data/processed/sprint23/validation/shadow_opportunity_ledger.csv`
- `data/processed/sprint23/validation/shadow_opportunities_graded.csv`
- `data/processed/sprint23/validation/shadow_validation_summary.csv`
- `data/processed/sprint23/validation/shadow_validation_catalog.json`

## Promotion policy

The system remains `SHADOW_ONLY`. Phase 4 never promotes a model automatically.

A model can only become `ELIGIBLE_FOR_REVIEW` after at least 200 graded markets, positive flat-stake ROI, and nonnegative average line CLV. That status only permits human review; it does not replace `models/props_models.pkl`, change staking, or publish live recommendations.

## Interpretation

- `profit_per_dollar`: hypothetical return from a flat $1 stake at the archived opening odds.
- `line_clv`: side-aware improvement versus the latest observed line. Positive is favorable.
- `price_clv`: change in market implied probability from opening odds to latest observed odds.
- `PENDING`: no verified final player stat is available yet.
