# Sprint 20 Phase 3 — Market Movement Intelligence

## Purpose

Turn immutable line snapshots into ordered market timelines and quantify how the market moved across DraftKings, FanDuel, and Fanatics.

## Engine

`wnba_market_movement_engine.py`

The engine reads `data/history/wnba_line_snapshots.jsonl`, links matching Phase 2 rankings, and produces:

- opening, current, and closing line/price
- ordered timeline
- directional movement from the selected side
- line and price move counts
- largest jump
- elapsed time and hourly velocity
- volatility, stability, movement, steam, and market-confidence scores
- steam alerts
- reverse line movement
- model-ahead, model-agreement, and model-disagreement classifications

## Detection rules

A steam alert requires at least two sportsbooks, at least 1.0 point of directional movement, and a movement window no longer than three hours when timestamps are available.

Reverse line movement is flagged when a matched model selection exists and the market moves at least 0.5 against that selection.

These are transparent operational rules, not proof that a move was caused by professional bettors.

## Outputs

- `data/history/market_movement_history.jsonl`
- `data/warehouse/market_movement.json`
- `data/dashboard/market_movement.json`

History uses a deterministic market key and updates existing markets instead of inserting duplicate records.

## Workflow

`WNBA Sprint 20 Phase 3 Market Movement`

The workflow can run manually with `open`, `snapshot`, or `close`, and runs automatically after a successful Phase 2 workflow. It captures the requested snapshot, builds movement intelligence, validates timeline ordering, and safely commits artifacts to `main`.

## Important operating note

Market movement becomes more informative after multiple scheduled captures. A single run creates a valid baseline but cannot establish meaningful velocity or multi-step movement by itself.
