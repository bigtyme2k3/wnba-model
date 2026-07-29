# GitHub Actions Workflow Audit

## Goal
Stabilize the WNBA dashboard and reduce workflow overlap without deleting useful model capabilities.

## Phase status
- Phase 1: Complete — canonical dashboard ownership and publish guard documented.
- Phase 2: Complete — dashboard build/publish logic removed from injury refresh, history repair, V4 status, and postgame learning workflows.
- Phase 3: Complete — production responsibilities and primary output ownership documented below.

## Canonical owners

### Dashboard HTML build
- `.github/workflows/wnba_v4_player_props_polish.yml`
- Sole workflow allowed to generate and publish `docs/index.html`.

### GitHub Pages deployment
- `.github/workflows/deploy_wnba_dashboard.yml`
- Deploys the already-built `docs/` directory.
- Does not rebuild dashboard content.

### Production QA and model-data build
- `.github/workflows/wnba_v4_status.yml`
- Produces current-slate model, master, warehouse, dashboard JSON, QA, mission-control, and status artifacts.
- Does not build or publish dashboard HTML.

### Results grading and learning
- `.github/workflows/wnba_postgame_learning_pipeline.yml`
- Owns final-game detection, grading, Phase 5 learning, backtesting, calibration, and learning-output publication.
- Does not build or publish dashboard HTML.

### Injury data refresh
- `.github/workflows/wnba_injury_refresh.yml`
- Owns injury refresh and injury-sensitive data/model outputs.
- Does not publish dashboard HTML.

### Historical player-prop repair
- `.github/workflows/wnba_player_props_history_repair.yml`
- Manual repair workflow for historical player context.
- Does not publish dashboard HTML.

## Primary data ownership map

| Output family | Primary owner | Consumers |
|---|---|---|
| `docs/index.html` | `wnba_v4_player_props_polish.yml` | GitHub Pages deploy |
| `data/master/wnba_master.json` | `wnba_v4_status.yml` for current slate; postgame pipeline may refresh after grading | Dashboard builder, model layers, QA |
| `data/dashboard/wnba_master.json` | Master source builder invoked by current-slate/status and postgame workflows | Dashboard builder |
| `data/dashboard/wnba_live_results_engine.json` | `wnba_postgame_learning_pipeline.yml` | Dashboard builder, grading monitor |
| `data/dashboard/wnba_live_games.json` | `wnba_postgame_learning_pipeline.yml` | Dashboard builder |
| `data/dashboard/wnba_phase5_learning.json` | `wnba_postgame_learning_pipeline.yml` | Dashboard builder, QA |
| `data/warehouse/wnba_phase5_learning.json` | `wnba_postgame_learning_pipeline.yml` | Learning and backtest layers |
| `data/history/wnba_graded_bets.csv` | `wnba_postgame_learning_pipeline.yml` | Learning, performance analysis |
| `config/wnba_learned_weights.json` | `wnba_postgame_learning_pipeline.yml` | Model calibration and later builds |
| `data/dashboard/wnba_mission_control.json` | `wnba_v4_status.yml` | Dashboard builder, health checks |
| `data/dashboard/wnba_market_intelligence.json` | `wnba_v4_status.yml` | Dashboard builder, decision engine |
| `data/dashboard/wnba_model_picks_ledger.json` | `wnba_v4_status.yml` with grading updates from postgame pipeline | Dashboard builder, learning |
| `data/dashboard/wnba_alt_market_warehouse.json` | `wnba_v4_status.yml` and dedicated injury/repair refreshes only when their domain changes | Dashboard builder, recommendation layers |
| `data/dashboard/wnba_*projection*.json` | `wnba_v4_status.yml` | Dashboard builder, QA, ranking layers |
| Injury-specific JSON/CSV | `wnba_injury_refresh.yml` | Model build, master source, dashboard builder |
| Historical repair artifacts | `wnba_player_props_history_repair.yml` | Warehouses, projection inputs |

## Ownership rules
1. Only the canonical dashboard workflow may publish `docs/index.html`.
2. Data workflows publish JSON, CSV, history, warehouse, model, and report artifacts only.
3. A downstream workflow should consume an owner's output instead of rebuilding dashboard HTML.
4. Repair and migration workflows remain manual-only unless a production dependency requires scheduling.
5. No workflow is deleted until its outputs and consumers are documented.

## Completed dashboard-writer cleanup

| Workflow | Final responsibility | HTML status |
|---|---|---|
| `wnba_injury_refresh.yml` | Injury refresh and injury-sensitive data | Removed |
| `wnba_player_props_history_repair.yml` | Manual historical repair | Removed |
| `wnba_v4_status.yml` | Current-slate production data and QA | Removed |
| `wnba_postgame_learning_pipeline.yml` | Results grading and learning data | Removed |
| `wnba_v4_player_props_polish.yml` | Canonical dashboard build | Retained |
| `deploy_wnba_dashboard.yml` | Pages deployment | Deploy only |

## Production dependency graph

```text
Data collection / injuries / historical repair
                    |
                    v
        Current-slate production build
                    |
                    v
           Model data + QA outputs
                    |
          +---------+---------+
          |                   |
          v                   v
 Postgame grading       Dashboard builder
 and learning                 |
          |                    v
          +------------> GitHub Pages deploy
```

## Core production architecture
1. Data foundation and source refresh
2. Injury refresh
3. Current-slate model/data build and QA
4. Results grading and learning
5. Canonical dashboard build
6. GitHub Pages deployment
7. Historical repair and migration workflows as manual-only utilities

## Remaining optimization backlog
These are later refinements, not blockers for Phase 2 or Phase 3 completion:
- Merge related dashboard patch scripts into a smaller ordered build module.
- Reduce duplicate invocation of master-source and ledger scripts where safe.
- Review every sprint-specific workflow and convert obsolete schedules to manual-only.
- Add machine-readable ownership metadata for exact JSON paths.
- Add CI that fails when a non-canonical workflow references `docs/index.html`.

## Safety rule
Do not delete workflows until their outputs and downstream dependencies are documented. Disable or convert them to manual-only first.
