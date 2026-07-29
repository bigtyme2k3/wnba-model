# GitHub Actions Workflow Audit

## Goal
Stabilize the WNBA dashboard and reduce workflow overlap without deleting useful model capabilities.

## Canonical owners

### Dashboard HTML build
- `.github/workflows/wnba_v4_player_props_polish.yml`
- Sole workflow allowed to publish `docs/index.html` through `scripts/atomic_generated_push.sh`.

### GitHub Pages deployment
- `.github/workflows/deploy_wnba_dashboard.yml`
- Deploys the already-built `docs/` directory.
- Does not rebuild dashboard content.

## Confirmed competing dashboard builders
These workflows rebuild or patch `docs/index.html`, but the shared atomic publish guard now prevents them from publishing the HTML unless they are the canonical dashboard workflow.

| Workflow | Current role | Recommendation |
|---|---|---|
| `wnba_injury_refresh.yml` | Refreshes injury data and rebuilds dashboard | Keep data/model refresh; remove dashboard build section after validation |
| `wnba_player_props_history_repair.yml` | Repairs historical prop context and rebuilds dashboard | Manual-only repair; remove dashboard build section after validation |
| `wnba_v4_status.yml` | Full production finalizer and complete dashboard build | Merge model/data build into core pipeline; stop publishing HTML |
| `wnba_postgame_learning_pipeline.yml` | Grades results, runs learning, rebuilds dashboard every 15 minutes when needed | Keep grading/learning; stop rebuilding dashboard HTML |
| `wnba_v4_player_props_polish.yml` | Builds and publishes current dashboard | Keep as canonical dashboard builder |
| `deploy_wnba_dashboard.yml` | Publishes GitHub Pages artifact | Keep as sole deployer |

## Immediate controls already applied
- `scripts/atomic_generated_push.sh` blocks non-canonical workflows from publishing `docs/index.html`.
- Other workflows may continue publishing their own JSON, CSV, history, and model artifacts.
- `deploy_wnba_dashboard.yml` remains a pure deploy workflow.

## Workflow classification framework

### Keep active
- Core data collection workflows
- Core odds and injury refresh workflows
- Results grading and learning workflows
- One canonical dashboard build workflow
- One GitHub Pages deploy workflow
- One production QA/integrity workflow

### Convert to manual-only
- Historical repair workflows
- Migration workflows
- One-time sprint repair workflows
- Backfill and reconstruction workflows

### Merge
- Overlapping market intelligence workflows
- Overlapping autonomous pipelines
- Multiple dashboard QA/status workflows
- Multiple ALT market refresh workflows

### Disable after dependency confirmation
- Sprint-specific repair workflows whose output is already produced by the core pipeline
- Workflows that only duplicate another active workflow
- Workflows that repeatedly rebuild `docs/index.html`

## Target production architecture
1. `WNBA Data Foundation`
2. `WNBA Model Build`
3. `WNBA Results and Learning`
4. `WNBA Dashboard Build`
5. `Deploy WNBA Dashboard`
6. `WNBA Production Health`

## Next audit steps
1. Inventory all workflow triggers and schedules.
2. Inventory every generated output path per workflow.
3. Detect duplicate writers for `data/dashboard/*.json` and `data/master/*.json`.
4. Mark historical and repair workflows as manual-only.
5. Consolidate the full dashboard build sequence into one script used only by the canonical dashboard workflow.
6. Remove dashboard rebuild steps from injury, status, history-repair, and postgame workflows.
7. Reduce active scheduled workflows to approximately 5–8 core workflows.

## Safety rule
Do not delete workflows until their outputs and downstream dependencies are documented. Disable or convert them to manual-only first.
