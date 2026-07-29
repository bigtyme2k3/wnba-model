# Sprint 25 Phase 1 — Best Bets Performance Database

## Purpose

Convert the immutable Sprint 24.1 Best Bets ledger into a gradeable performance database that learns from every archived recommendation.

## Inputs

- `data/history/best_bets_ledger.csv`
- `data/history/wnba_projection_history.jsonl`
- `data/dashboard/wnba_market_intelligence.json`

## Outputs

- `data/history/best_bets_performance.csv`
- `data/history/best_bets_performance_summary.json`

## Grading

Each ledger snapshot receives:

- actual result
- WIN / LOSS / PUSH / PENDING
- closing line
- closing odds when available
- line CLV
- odds CLV probability
- flat one-unit stake
- profit units
- ROI
- grading timestamp
- days since prediction

American odds are converted to decimal payout for flat-unit profit calculation. A win returns the profit portion of a one-unit stake, a loss returns `-1.0`, and a push returns `0.0`.

## Data integrity

The immutable ledger remains unchanged. The performance database is rebuilt deterministically from the ledger and current actual/market sources. `snapshot_id` remains the unique key and duplicates fail validation.

## Workflow order

1. Generate final Best Bets card.
2. Apply correlation, evidence, deduplication, and live-slate gates.
3. Archive immutable Best Bets ledger.
4. Grade and enrich the performance database.
5. Validate both databases.
6. Publish generated history files and dashboard.

## Commands

```bash
python grade_best_bets.py
python grade_best_bets.py --validate-only
```

## Summary metrics

The summary JSON includes total Best Bets, graded and pending counts, wins, losses, pushes, win rate, profit units, ROI, average line CLV, and positive CLV rate.
