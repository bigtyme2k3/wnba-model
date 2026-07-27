# Sprint 20.5 Phase D — Probability Calibration and Out-of-Sample Validation

Phase D tests whether a calibration method improves `simulation_probability` on unseen later outcomes.

## Method

Settled model history is sorted chronologically. The earliest 70% is used for fitting and the latest 30% is reserved for validation. No validation outcome is used to fit a calibrator.

Candidate methods:

- Identity/raw probability
- Temperature scaling
- Linear shrinkage toward 50%
- Platt scaling
- Isotonic regression

## Metrics

Each candidate is evaluated on the held-out period using:

- Brier score
- Log loss
- Expected calibration error
- Calibration bands

## Deployment gate

A non-identity calibrator is enabled only when all conditions pass:

- At least 500 training records
- At least 200 validation records
- Log-loss improvement of at least 0.01
- Brier-score improvement of at least 0.005
- Positive ECE improvement

Otherwise the generated calibrator remains disabled and preserves the raw probability path.

## Outputs

- `data/audit/phase_d_calibration_validation.json`
- `data/audit/phase_d_validation_curves.json`
- `data/warehouse/wnba_probability_calibrator.json`

The calibrator artifact preserves both intended fields:

- `raw_simulation_probability`
- `calibrated_probability`

Phase D validates and selects a method. It does not yet rewrite the edge database or EV calculations; integration occurs only after the deployment gate passes and the production report is reviewed.
