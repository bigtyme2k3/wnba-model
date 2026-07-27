# Sprint 19 Phase 2 — Closing Line Value

## Objective

Connect every Phase 1 edge record to opening, bet-time, and closing market observations so the model can measure whether it consistently beats the market.

## Inputs

- `data/history/wnba_edge_database.jsonl`
- `data/history/wnba_line_snapshots.jsonl`

## Outputs

- enriched `data/history/wnba_edge_database.jsonl`
- `data/warehouse/wnba_clv_edge_report.json`
- `data/dashboard/wnba_clv_edge_report.json`

## Record enrichment

Each matched edge record receives:

- opening line and price
- bet-time line and price
- closing line and price
- opening-to-bet line movement
- directional line CLV
- implied-probability price CLV
- CLV grade: positive, negative, neutral, or pending
- snapshot timestamps and CLV status

Directional line CLV is positive when the selected side receives a better number than the closing market. Price CLV is positive when the closing implied probability is higher than the entry implied probability.

## Reporting

The Phase 2 report includes:

- total edge and snapshot records
- linked and graded record counts
- closing-line coverage rate
- positive, negative, and neutral CLV counts
- positive CLV rate
- average line and price CLV
- CLV performance by market and sportsbook
- win rate within each CLV bucket
- top positive and largest negative CLV records

## Reliability rules

- Matching uses date, player, game, market, and selection.
- The selected sportsbook is preferred when book-specific snapshots exist.
- Repeated runs update the existing edge record and never create duplicates.
- Missing closing lines remain pending rather than being scored as neutral.
- Workflow pushes use fetch/rebase retry protection.

## Acceptance criteria

- American-odds and directional CLV math pass deterministic QA.
- Opening, bet-time, and closing observations attach to the correct edge record.
- Over and under directional calculations are correct.
- Repeated runs remain idempotent.
- Dashboard and warehouse reports contain all required coverage and performance fields.
- The workflow can run manually and automatically after line snapshots or Phase 1 updates.
