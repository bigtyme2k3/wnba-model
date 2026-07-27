# Sprint 19 Phase 1 — Edge Database

## Objective

Create one durable source of truth for every WNBA model decision so projections can be evaluated against sportsbook prices, closing lines, and final results.

## Canonical outputs

- `data/history/wnba_edge_database.jsonl` — append-safe, deduplicated historical records
- `data/warehouse/wnba_edge_database.json` — full analytical summary
- `data/dashboard/wnba_edge_database.json` — dashboard-ready copy

## Record schema

Each edge record includes:

- date, player, team, game, market, and selection
- model projection and sportsbook line
- projection edge and edge percentage
- American odds and sportsbook
- implied probability and model probability
- probability edge
- expected value and expected-value percentage
- confidence, consensus score, and engine agreement
- recommendation and bet eligibility
- stake, status, result, actual value, profit/loss, and ROI
- closing line and CLV
- decision reason and guardrail failures

## Data flow

1. `wnba_historical_database.py` archives model decisions.
2. `wnba_results_grader.py` updates outcomes, actual values, and profit/loss.
3. `wnba_edge_database.py` normalizes and upserts records using the historical key.
4. The workflow writes warehouse and dashboard summaries.

The database does not place bets. It records model recommendations and performance data for analysis.

## Reliability rules

- Duplicate records are prevented with a deterministic edge key.
- Re-running the same slate is idempotent.
- Settled results update existing records rather than creating duplicates.
- Invalid, missing, or non-finite values are stored as `null`.
- Expected value is calculated from model probability and American odds when both are available.
- Existing EV fields are used only when a probability-based calculation is unavailable.

## Summary metrics

The warehouse report provides:

- total, open, settled, and target-date record counts
- win rate
- total stake
- profit/loss
- ROI
- average expected value
- performance by market
- top target-date edges
- recent records

## Acceptance criteria

- Probability and American-odds calculations pass deterministic QA.
- A new prediction is inserted exactly once.
- A repeated run creates no duplicate.
- A graded result updates the original record.
- Warehouse and dashboard JSON artifacts are non-empty and contain required fields.
- The Phase 1 workflow runs after a successful Intelligence Foundation workflow and can also be started manually.
