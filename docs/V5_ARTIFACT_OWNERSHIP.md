# WNBA V5 Artifact Ownership

Status: **enforced maintenance-mode production contract**.

The machine-readable source of truth is `config/v5_artifact_ownership.json`. The blocking workflow `.github/workflows/wnba-v5-artifact-ownership-audit.yml` scans all active workflows and fails when the declared ownership or maintenance schedule contract is violated.

## Core rule

Every protected production artifact has exactly one authoritative workflow writer. Other modules may consume it, validate it, archive immutable snapshots, or render it, but they must not independently publish a competing canonical copy.

Clock schedules are orchestration triggers, not ownership. Research jobs should normally run when their evidence changes. Dashboard/deploy jobs are presentation consumers and must not regenerate upstream model evidence.

## Canonical chain

`SCHEDULE -> ODDS -> PROPS -> CONTEXT -> PREDICTIONS -> FORWARD LEDGER -> CLOSE -> RESULTS -> LEARNING -> DASHBOARD`

The current production ownership is declared artifact-by-artifact in `config/v5_artifact_ownership.json`. The key workflow owners are:

| Domain | Canonical artifact / evidence | Authoritative workflow writer | Allowed downstream behavior |
| --- | --- | --- | --- |
| Schedule / slate | `data/dashboard/wnba_master.json` | `wnba_daily_canonical_build.yml` | Read, validate target date, derive views |
| Standard player props | `data/dashboard/wnba_player_props.json` | `wnba_daily_canonical_build.yml` | Score/model; downstream M02 may reuse the current canonical snapshot |
| Injury context | dashboard + warehouse injury intelligence | `wnba_v5_injury_dashboard.yml` | Prediction issuance consumes current source-only context; old issuance is never backfilled |
| Base game predictions | `wnba_sprint2_predictions.json` | `wnba_daily_canonical_build.yml` | Injury-aware Phase 2 consumes it |
| Injury-aware game / M02 predictions | Phase 2 + M02 prediction artifacts | `wnba-new-day-prediction-sync.yml` | Dashboard, M12 and evidence consumers read them |
| Forward evidence | `data/history/wnba_v5_forward_predictions.jsonl` | `wnba-v5-m12-postgame-learning.yml` | Immutable issuance/finalization rules; challengers consume only |
| Closing lines | explicit close CSV/snapshot/CLV queue | `wnba-v5-s3-m02-closing-capture.yml` | Only verified explicit close in the valid pre-tip window |
| Results | model history + results lifecycle | `wnba_results_refresh.yml` | Learning consumes resolved outcomes; dashboard renders |
| ALT market | dashboard + warehouse ALT market state | `wnba_alt_pregame_snapshot.yml` | Streaks, parlays and performance consume it |
| Dashboard freshness | `data/dashboard/wnba_tab_freshness.json` | `wnba_daily_slate_rollover.yml` | Deploy/render consumes it |

## Daily orchestration

There is now one dependency-order production entry point:

`.github/workflows/wnba-v5-daily-orchestrator.yml`

It does not own upstream artifacts. It calls reusable authoritative stages in order:

`OWNERSHIP PREFLIGHT -> CANONICAL BASE -> INJURY CONTEXT -> PHASE 2 / M02 -> DERIVED DASHBOARD -> DEPLOY`

The four core stage workflows support `workflow_call` and remain directly manually dispatchable for targeted QA. The orchestrator requires explicit `live_mode=true` before any production stage runs. During maintenance mode it has no clock schedule.

Closing capture, results/grading, ALT ingestion, M12 forward evidence and research evaluation remain domain-specific workflows because they run on different evidence timing and should not be forced into morning slate creation.

## Maintenance-mode certification

The enforced ownership report currently requires:

- zero ownership violations;
- zero scheduled workflows;
- zero scheduled paid-API risks;
- zero scheduled live-pipeline risks.

The contract is intentionally stricter during the 2026 FIBA break. Automatic clocks must not be reintroduced by an unrelated workflow edit.

## Slate QA gates

`.github/workflows/wnba-v5-empty-slate-contract.yml` is an offline, read-only slate contract suite. It runs both scenarios entirely in temporary directories:

1. **Confirmed empty slate** — zero games, zero props, zero bets/portfolio, no Odds API call and no `player_points.py` execution.
2. **Controlled active slate** — one synthetic game using a persisted three-book canonical prop fixture, no live Odds API call, one deterministic M02 projection, and no mutation of repository production data.

Both tests must leave `git diff` clean. These tests are the pre-live structural gate; a real active-slate production run is still a separate operator-controlled step.

## Live market capture

Live workflows may run frequently only when the source can materially change. They should publish only artifacts in their domain. A closing-line capture workflow must not become a broad dashboard rebuild.

## Results and grading

Results recovery owns completed actuals and grading. It is separate from current-slate generation. Regrading may update derived performance but may not rewrite immutable prediction issuance.

## Research

Drift, feature lineage, champion/challenger, adaptive challenger, calibration and promotion-readiness modules consume evidence. They should trigger on evidence/code changes or manual QA rather than repeatedly rewriting unchanged reports on a clock.

## Dashboard / deploy

Deployment is a terminal consumer. Renderer patches are presentation-only by default. A dashboard build failure must never be "fixed" by silently rerunning an upstream evidence producer inside a renderer.

## Invariants

1. One canonical workflow writer per protected production artifact.
2. Immutable forward issuance: earliest valid issuance remains historical truth.
3. No lookahead: contextual features must exist at issuance time.
4. Explicit close only: no inferred closing prices.
5. Target-date validation at every production boundary.
6. Empty slate is a valid READY state and must clear stale current-slate rows.
7. No-op publish is success when the workflow contract permits unchanged output.
8. Research cannot promote itself into production; promotion requires explicit evidence gates.
9. Paid APIs are called only by source owners and only when cached/current canonical evidence cannot satisfy the contract.
10. Dashboard code reads canonical artifacts; it does not own them.
11. The orchestrator owns dependency order, not the artifacts produced by its called stages.
12. Maintenance mode contains no automatic cron execution.

## Re-enable sequence

Before live schedules return:

1. Ownership contract must remain PASS.
2. Offline empty-slate contract must pass.
3. Offline active-slate simulation must pass without paid API access.
4. Run one operator-controlled real active slate through the V5 orchestrator with `live_mode=true`.
5. Verify target-date consistency, source immutability, forward issuance, explicit-close readiness, grading handoff and terminal dashboard deployment.
6. Change `config/v5_artifact_ownership.json` from maintenance to the approved live schedule contract.
7. Re-enable only the minimum required source/evidence schedules, then let the blocking audit enforce the new live contract.
