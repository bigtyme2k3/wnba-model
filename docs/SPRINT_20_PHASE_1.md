# Sprint 20 Phase 1 — Line Shopping

## Objective

Choose the best available WNBA line and price across DraftKings, FanDuel, and Fanatics for every supported market.

## Data flow

1. `wnba_sportsbook_consensus.py` normalizes current target-date odds and restricts books to DK, FD, and Fanatics.
2. `wnba_line_shopping_engine.py` creates separate over and under shopping records.
3. The engine stores consensus line/probability, best book, best odds, implied probability, price advantage, line range, and disagreement score.
4. History is upserted by deterministic shopping key and repeated runs are idempotent.

## Outputs

- `data/history/line_shopping_history.jsonl`
- `data/warehouse/market_intelligence.json`
- `data/dashboard/market_intelligence.json`

## Acceptance criteria

- Only DraftKings, FanDuel, and Fanatics are accepted.
- Positive American odds and negative American odds convert correctly.
- Best price selection prefers the highest American price.
- Multi-book and three-book market coverage are reported.
- Identical reruns insert and update zero records.
- Dashboard and warehouse artifacts contain the required summary fields.
- Artifact pushes retry safely after concurrent updates to `main`.
