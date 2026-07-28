# Sprint 21 Phase 3 — Advanced Feature Engineering and Model Rebuild

## Objective

Create leakage-safe pregame features and determine whether they produce a genuine ranking signal under expanding-window validation.

## Feature engineering

The builder creates only features available before settlement:

- absolute and signed-log transformations of numeric pregame fields
- selected interactions and differences among CLV, EV, edge, line and market-depth fields
- sportsbook implied probability from American odds
- model-versus-market probability gap when both inputs exist
- strictly lagged player and market win-rate context

Postgame values such as `actual`, outcome, payout and profit are excluded from current-row feature construction. Lagged outcome features use only records earlier in chronological order.

## Candidate models

Phase 3 compares several regularized logistic configurations:

- baseline regularized
- compact engineered
- extended engineered
- strongly regularized engineered

This dependency-free comparison is designed to run reliably in GitHub Actions. More complex estimators should only be added after the engineered data demonstrates repeatable signal.

## Validation

Each candidate is evaluated with expanding chronological folds. Metrics include:

- ROC AUC
- Brier score
- log loss
- expected calibration error
- top-versus-bottom decile win-rate spread
- fold stability
- market-specific diagnostics when sample size permits

## Deployment gate

A model advances only when it has:

- AUC of at least 0.53
- decile spread of at least 0.08
- stability score of at least 0.50
- at least three valid chronological folds

Phase 3 never changes production predictions, probabilities or EV calculations. Even a passing candidate remains disabled until a later shadow-production phase.

## Outputs

- `data/audit/sprint21_phase3_feature_manifest.json`
- `data/audit/sprint21_phase3_model_comparison.json`
- `data/audit/sprint21_phase3_best_model.json`
- `data/audit/sprint21_phase3_market_models.json`
