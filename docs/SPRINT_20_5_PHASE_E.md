# Sprint 20.5 Phase E — Ranking Signal and Market Calibration Validation

Phase E prevents a calibration method from being deployed merely because it improves Brier score, log loss, or ECE by collapsing every prediction toward the historical base rate.

## Validation scope

- Chronological 70/30 settled-record split
- Raw and calibrated ROC AUC
- Top-decile versus bottom-decile win-rate spread
- Raw and calibrated probability range
- Calibration by market
- Calibration by over/under direction
- Market-direction segment diagnostics
- Preserved-ranking deployment gate

## Deployment gate

Calibrated EV remains disabled unless all conditions pass:

- Raw validation AUC is at least 0.53
- Top-minus-bottom decile win-rate spread is at least 0.08
- Calibration loses no more than 0.01 AUC
- Calibrated probabilities span at least 0.08
- Phase D calibration improvements remain valid

A HOLD result means the probability signal must be rebuilt or segmented before it is used for expected-value calculations.

## Outputs

- `data/audit/phase_e_ranking_market_validation.json`
- `data/audit/phase_e_segment_validation.json`
- `data/warehouse/wnba_calibration_deployment_policy.json`

This phase does not modify the edge database, opportunity finder, or production EV calculations.
