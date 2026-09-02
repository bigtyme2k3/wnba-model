# WNBA V5 Artifact Ownership

Status: architecture contract for maintenance-mode consolidation.

## Core rule

Every production artifact has exactly one authoritative writer. Other modules may consume it, validate it, archive immutable snapshots, or render it, but they must not independently regenerate or overwrite the same canonical artifact.

Clock schedules are orchestration triggers, not ownership. Research jobs should normally run when their evidence changes. Dashboard/deploy jobs are presentation consumers and must not regenerate upstream model evidence.

## Canonical chain

`SCHEDULE -> ODDS -> PROPS -> CONTEXT -> PREDICTIONS -> FORWARD LEDGER -> CLOSE -> RESULTS -> LEARNING -> DASHBOARD`

| Domain | Canonical artifact / evidence | Authoritative writer | Allowed downstream behavior |
| --- | --- | --- | --- |
| Schedule / slate | `data/dashboard/wnba_master.json` and current-slate representation | `wnba_current_slate.py` | Read, validate target date, derive views |
| Game odds | canonical current sportsbook/game-market artifacts | `wnba_odds_ingestion.py` | Normalize, compare, derive market intelligence |
| Standard player props | `data/dashboard/wnba_player_props.json` | `wnba_player_props_ingestion.py` | Score/model; M02 may reuse current canonical props but must not create a competing canonical feed |
| ALT props | exact ALT market warehouse | `wnba_alt_market_warehouse.py` after authenticated ALT ingestion | Streaks, parlay builder, performance consume warehouse |
| Injury / rotation context | `data/dashboard/wnba_v5_injury_intelligence.json` plus frozen issuance context | injury/context refresh pipeline | Prediction issuance freezes a snapshot; old issuance rows are never backfilled |
| Current predictions | M11/current prediction artifact | canonical V5 inference path | Dashboard renders; M12 records immutable issuance evidence |
| Forward evidence | `data/history/wnba_v5_forward_predictions.jsonl` | M12 postgame/forward-ledger writer | Append/finalize only under immutable-ledger rules; challengers consume only |
| Closing lines | explicit-close artifacts | S3 M02 closing capture | Only verified explicit close in valid pre-tip window; never infer a close |
| Results / actuals | verified game/player actual warehouse and grading outputs | results/actual recovery + grader | Learning consumes resolved outcomes; dashboard renders |
| Learning / evaluation | M12 reports, forward diagnostics, champion/challenger reports | evidence-specific evaluator | Research-only until promotion gates pass; never mutate historical issued probabilities |
| Dashboard | generated dashboard/UI artifacts | deploy/dashboard builder | Presentation only; must not rerun M03/M12 or reconstruct upstream evidence |

## Orchestration ownership

### Daily orchestration

Long-term there should be one active daily orchestrator. Its job is to call source owners in dependency order and verify their outputs. It must not contain alternate implementations of those owners.

During the 2026 FIBA break, the overlapping scheduled writers (`wnba_daily_canonical_build.yml`, `wnba-new-day-prediction-sync.yml`, and `wnba_daily_slate_rollover.yml`) remain maintenance/manual only while consolidation is performed.

### Live market capture

Live workflows may run frequently only when the source can materially change. They should publish only the artifacts in their domain. A closing-line capture workflow should not become a broad dashboard rebuild.

### Results and grading

Results recovery owns completed actuals and grading. It is separate from current-slate generation. Regrading may update derived performance but may not rewrite immutable prediction issuance.

### Research

Drift, feature lineage, champion/challenger, adaptive challenger, calibration and promotion-readiness modules consume evidence. They should trigger on evidence/code changes or manual QA rather than repeatedly rewriting unchanged reports on a clock.

### Dashboard / deploy

Deployment is a terminal consumer. Renderer patches are presentation-only by default. A dashboard build failure must never be "fixed" by silently rerunning an upstream evidence producer inside a renderer.

## Invariants

1. One canonical writer per production artifact.
2. Immutable forward issuance: earliest valid issuance remains historical truth.
3. No lookahead: contextual features must exist at issuance time.
4. Explicit close only: no inferred closing prices.
5. Target-date validation at every production boundary.
6. Empty slate is a valid state, not automatically a pipeline failure.
7. No-op publish is success when the workflow contract permits unchanged output.
8. Research cannot promote itself into production; promotion requires explicit evidence gates.
9. Paid APIs are called only by source owners and only when cached/current canonical evidence cannot satisfy the contract.
10. Dashboard code reads canonical artifacts; it does not own them.

## Consolidation order

1. Restore/preserve all validation checks in maintenance-mode daily workflows.
2. Inventory every writer of the schedule, props, prediction, forward-ledger, close, result and dashboard artifacts.
3. Mark non-authoritative writers as consumers or retire them.
4. Replace overlapping daily workflows with one orchestrator that calls authoritative stages.
5. Narrow publish scopes by domain to reduce Git races.
6. Add an automated ownership audit that fails when a protected canonical artifact gains multiple production writers.
7. Re-enable schedules only after an empty-slate QA run and a controlled active-slate simulation both pass.
