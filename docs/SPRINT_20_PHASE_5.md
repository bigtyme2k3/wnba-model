# Sprint 20 Phase 5 — Professional Dashboard

Phase 5 completes the Sprint 20 market-intelligence platform by combining the outputs of Phases 1–4 into one mobile-friendly command center.

## Inputs

- `data/dashboard/market_intelligence.json`
- `data/dashboard/wnba_opportunity_rankings.json`
- `data/dashboard/market_movement.json`
- `data/dashboard/opportunity_finder.json`
- `data/dashboard/wnba_clv_summary.json`
- `data/history/opportunity_finder_history.jsonl`

## Outputs

- `data/warehouse/professional_dashboard.json`
- `data/dashboard/professional_dashboard.json`
- `docs/data/professional_dashboard.json`
- `docs/index.html`

## Dashboard sections

- Executive market summary
- Top opportunities and highest EV
- Arbitrage and middle opportunities
- Steam alerts and largest moves
- Best sportsbook and line-shopping views
- Opportunity, market, and recommendation distributions
- CLV and source-health indicators

## Operation

The workflow can be run manually or automatically after a successful Phase 4 Opportunity Finder run. It validates the aggregator, builds all dashboard payloads, verifies the GitHub Pages asset, and commits generated artifacts to `main`.

The dashboard reports analytics only. It does not place wagers.
