# Sprint 21 Phase 2 — Feature Set Optimization & Rolling Validation

## Objective

Compare leakage-safe candidate feature sets on strictly later unseen WNBA outcomes using expanding-window rolling validation.

## Critical leakage safeguard

Sprint 21 Phase 1 identified `actual` as a strong feature because it is directly tied to the settled result. It is postgame information and cannot be used for prediction. Phase 2 therefore excludes `actual`, outcome fields, result fields, settlement fields, payout/profit fields, and other postgame values before any model is fit.

## Candidate sets

- `core`: Phase 1 keep features after leakage removal.
- `core_plus_review`: safe keep and review features.
- `minimal_ranked`: strongest safe Phase 1-ranked features.
- `core_plus_engineered`: safe core plus existing pregame market features.
- `current_numeric`: current numeric baseline after leakage removal.

## Validation design

- Records are ordered chronologically.
- Every fold trains only on records before its validation block.
- The training window expands over time.
- Missing values are imputed from training data only.
- Features are standardized using training statistics only.
- A regularized logistic model is fit independently in every fold.

## Metrics

- ROC AUC
- Brier score
- Log loss
- Expected calibration error
- Top-versus-bottom decile win-rate spread
- Stability across folds
- Validation sample size

## Deployment gate

A candidate is not recommended for the rebuilt engine unless it:

1. reaches at least 0.53 rolling AUC;
2. produces at least an 8-point top-to-bottom decile spread;
3. has a stability score of at least 0.50; and
4. improves AUC over the current safe numeric baseline by at least 0.01.

A `HOLD` result is valid and means the stored data does not yet support replacing the current model.

## Outputs

- `data/audit/feature_set_comparison.json`
- `data/audit/rolling_validation_results.json`
- `data/audit/best_feature_set.json`
- `data/audit/market_feature_recommendations.json`

## Safety

Phase 2 does not modify production predictions, probabilities, EV calculations, or betting recommendations. A passing feature set becomes a candidate for the market-specific model build in Sprint 21 Phase 3.
