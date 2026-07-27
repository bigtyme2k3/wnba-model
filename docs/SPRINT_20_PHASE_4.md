# Sprint 20 Phase 4 — Opportunity Finder

Phase 4 converts the market-intelligence stack into a concise daily decision layer.

## Inputs

- `data/warehouse/wnba_opportunity_rankings.json`
- `data/warehouse/market_intelligence.json`
- `data/warehouse/market_movement.json`
- `data/warehouse/wnba_sportsbook_consensus.json`
- `data/raw/line_shopping_<date>.csv` when available

Only DraftKings, FanDuel, and Fanatics are used for sportsbook comparisons.

## Features

- Positive-EV opportunity filtering
- Unified Opportunity Index from ranking, EV, movement, line shopping, confidence, and CLV
- Recommendations: `STRONG BET`, `BET`, `LEAN`, and `PASS`
- Market-disagreement, price-outlier, line-outlier, model-ahead, and steam flags
- Two-way arbitrage and near-arbitrage detection
- Cross-book middle detection
- Deterministic historical upserts
- Dashboard-ready Top Opportunities, Highest EV, Arbitrage, Middles, and Market Inefficiencies sections

## Outputs

- `data/history/opportunity_finder_history.jsonl`
- `data/warehouse/opportunity_finder.json`
- `data/dashboard/opportunity_finder.json`

## Recommendation thresholds

- Strong Bet: Opportunity Index at least 82, EV at least 8%, and model eligibility
- Bet: Opportunity Index at least 68, EV at least 4%, and model eligibility
- Lean: Opportunity Index at least 55, positive EV, and model eligibility
- Pass: all other records

A recommendation is a model classification, not a guarantee of profit. The system records the best available book and price but does not place wagers.

## Arbitrage and middle definitions

A two-way arbitrage exists when the best Over and Under implied probabilities total less than 1.00. A near-arbitrage is retained when the total is between 1.00 and 1.03 because it can reveal unusually efficient or mispriced markets.

A middle is flagged when the lowest available Over line is below the highest available Under line across supported sportsbooks. The workflow reports the window and books but does not assume both wagers are profitable without considering prices.

## Workflow

`WNBA Sprint 20 Phase 4 Opportunity Finder` can be run manually or automatically after a successful Phase 3 workflow. It compiles the code, runs isolated QA, generates artifacts, validates output ordering and recommendation values, removes Python cache files, and commits changes to `main` with retry protection.
