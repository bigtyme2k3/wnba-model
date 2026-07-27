# Sprint 21 Phase 1 — Feature Importance & Signal Audit

## Objective

Identify which numeric fields in settled WNBA model history contain repeatable predictive signal before rebuilding market-specific probability models.

Phase E showed that the current simulation probability has nearly random held-out ranking power. Phase 1 therefore audits the information entering the model rather than changing algorithms blindly.

## Audit engine

`audit_sprint21_phase1_feature_signals.py` automatically discovers numeric candidate features from `data/history/wnba_model_history.jsonl` and excludes identifiers, outcomes, labels, text fields, and operational metadata.

Each eligible feature is evaluated using:

- Pearson correlation with win/loss outcome
- Univariate ROC AUC
- Direction-adjusted AUC
- Top-versus-bottom 20% win-rate separation
- Quantile-based mutual information
- Stability across chronological periods
- Missing-value rate
- High-correlation redundancy detection

## Feature grades

The combined signal score produces a conservative grade:

- **A** — strong repeatable signal
- **B** — useful signal
- **C** — marginal or redundant; review
- **D** — weak; removal candidate
- **F** — no meaningful evidence of signal

Sample size, missingness, and redundancy can reduce a feature's effective grade.

## Outputs

- `data/audit/feature_importance.json`
- `data/audit/feature_rankings.json`
- `data/audit/feature_correlations.json`
- `data/audit/recommended_feature_set.json`

The recommended feature set separates fields into `keep`, `review`, and `remove_candidates`.

## Safety and interpretation

This is a univariate signal audit. A feature can be weak by itself but useful in interaction with other fields, and correlation does not prove causation.

No production model or EV calculation is changed in Phase 1. Feature removal requires market-specific rolling validation in Sprint 21 Phase 2.

## Workflow

Run:

**WNBA Sprint 21 Phase 1 Feature Signal Audit**

The workflow compiles the code, runs deterministic QA, generates and verifies all four artifacts, then commits production reports to `main`.
