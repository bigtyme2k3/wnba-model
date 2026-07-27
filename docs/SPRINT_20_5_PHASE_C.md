# Sprint 20.5 Phase C — Simulation Probability Calibration Audit

## Purpose

Phase A proved the odds, implied-probability, EV, and dashboard percentage calculations are mathematically consistent. Phase B proved the edge database correctly selects `simulation_probability`. Phase C evaluates whether those simulation probabilities are statistically calibrated against settled outcomes.

## Audit scope

`audit_phase_c_simulation_calibration.py` analyzes:

- Current-slate probability distribution
- Counts in probability bands from below 50% through 99–100%
- Extreme current probabilities at or above 95% or at or below 5%
- Historical settled WIN/LOSS records
- Brier score
- Log loss
- Expected calibration error (ECE)
- Maximum calibration error (MCE)
- Global predicted probability versus actual win rate
- Calibration curves by probability band
- Calibration diagnostics by market
- Historical performance of extreme predictions

## Diagnostic calibration candidates

The audit compares the unmodified probability stream with simple diagnostic transformations:

- Temperature scaling over a fixed parameter grid
- Linear shrinkage toward 50% over a fixed parameter grid

These are in-sample diagnostics only. The report must not be treated as authorization to deploy a calibration method directly. Any production correction must be trained on earlier dates and evaluated on later, untouched dates.

## Outputs

- `data/audit/phase_c_calibration_report.json`
- `data/audit/probability_calibration_curve.json`
- `data/audit/simulation_distribution.json`

## Status rules

The audit returns `WARN` when one or more of these conditions is detected:

- Fewer than 50 settled probability records
- Global overconfidence greater than five percentage points
- ECE above 0.08
- Extreme-probability overconfidence with a meaningful sample
- A diagnostic calibration candidate improves both probabilistic scoring diagnostics

A warning does not mean the ranking model is useless. It means raw probabilities should not be interpreted as trustworthy betting probabilities until time-split calibration validation is complete.

## Production workflow

Run **WNBA Sprint 20.5 Phase C Calibration Audit** from GitHub Actions on `main`. Leave the date blank to use the current UTC slate.

The workflow compiles the code, runs deterministic QA, builds all three audit artifacts, verifies their schemas, and commits changed artifacts back to `main`.

## Next decision

The Phase C production report determines whether the next step is:

1. Continue monitoring without changing the simulator.
2. Build a time-split calibration validator.
3. Recalibrate simulation probabilities while preserving ranking performance.
4. Investigate market-specific or model-component-specific overconfidence.

Do not hard-cap probabilities solely to make EV values appear realistic. Calibration must be supported by historical out-of-sample evidence.
