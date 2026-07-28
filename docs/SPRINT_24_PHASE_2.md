# Sprint 24 Phase 2 — Live Market Integration

This phase connects the existing current Odds API line-shopping feed to the canonical V2 market warehouse used by the active-slate scanner.

## Root cause fixed

`line_shopping.py` produced current sportsbook rows in `data/raw/line_shopping_today.csv`, while the active scanner read `data/warehouse/wnba_odds_warehouse_v2.sqlite`. No bridge existed, so the scanner evaluated only old warehouse snapshots and reported zero current markets.

## Pipeline

1. Collect current DraftKings and FanDuel game lines.
2. Collect only the five modeled player-prop markets for events inside 48 hours.
3. Write the existing line-shopping CSV schema.
4. Ingest those exact rows into the V2 warehouse.
5. Rebuild timeline, movement, steam, CLV, closing-line, opportunity, and active-slate artifacts.
6. Refresh Sprint 23 shadow opportunities and Sprint 24 governance.
7. Fail QA unless upcoming markets reach the active scanner.

## Credit controls

The collector requests only DraftKings and FanDuel and only these modeled props:

- points
- rebounds
- assists
- three-pointers
- points + rebounds + assists

No synthetic lines or prices are created.

## Safety

The phase remains shadow-only. It does not change production recommendations, staking, bankroll settings, or model promotion status.
