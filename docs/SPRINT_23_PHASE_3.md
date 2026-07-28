# Sprint 23 Phase 3 — Shadow Market Opportunity Scoring

Phase 3 compares the Sprint 23 shadow player-prop projections with exact sportsbook lines from the existing line-shopping feed.

## Scope

- DraftKings and FanDuel only.
- Points, rebounds, assists, three-pointers, and PRA.
- Over and under markets.
- Shadow outputs only; no production recommendation, staking, EV threshold, or dashboard logic is replaced.

## Inputs

- `data/features/sprint23/player/player_latest_features.csv`
- `models/sprint23/props_models_shadow.pkl`
- `models/sprint23/props_shadow_evaluation.json`
- `data/raw/line_shopping_today.csv`

## Outputs

- `data/processed/sprint23/props_market_opportunities_shadow.csv`
- `data/processed/sprint23/props_market_unmatched_shadow.csv`
- `data/processed/sprint23/props_market_opportunity_catalog.json`

## Scoring

The model projection is compared with each exact book line. Holdout MAE is converted to an approximate normal-distribution scale to estimate over/under probability. Listed American odds are converted to implied probability and expected profit per $1 staked.

These values are experimental ranking signals, not validated betting probabilities. Promotion remains `SHADOW_ONLY` until out-of-sample line-result and CLV tracking are completed.
