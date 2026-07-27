# Sprint 20 Phase 2 — Opportunity Ranking

## Purpose

Rank the active WNBA betting slate by combining model edge with the best available price from DraftKings, FanDuel, and Fanatics.

## Inputs

- `data/warehouse/market_intelligence.json` — Phase 1 best-book line shopping
- `data/history/wnba_edge_database.jsonl` — model probability, EV, confidence, results, and CLV

## Scoring

The 0–100 opportunity score uses:

- Expected value: 35%
- Probability edge: 20%
- Model confidence: 15%
- CLV: 15%
- Line-shopping price advantage: 10%
- Market depth: 5%

When a historical component such as CLV is unavailable, its weight is redistributed across the components that are available. Missing information therefore does not automatically become a positive or negative signal.

## Tiers

- **A:** score at least 80 and EV at least 8%
- **B:** score at least 68 and EV at least 4%
- **C:** score at least 55 with positive EV
- **PASS:** non-positive EV, ineligible recommendation, or score below the threshold

A and B opportunities are labeled `BET`, C opportunities are labeled `LEAN`, and all others are labeled `PASS`.

## Outputs

- `data/history/wnba_opportunity_ranking_history.jsonl`
- `data/warehouse/wnba_opportunity_rankings.json`
- `data/dashboard/wnba_opportunity_rankings.json`

The history file uses deterministic market keys and updates records only when ranking inputs materially change.

## Workflow

`WNBA Sprint 20 Phase 2 Opportunity Ranking` runs manually or after a successful Phase 1 workflow. It refreshes the edge database and CLV link, builds rankings, verifies sorted scores and required artifacts, and safely pushes updated data to `main` with fetch/rebase retries.
