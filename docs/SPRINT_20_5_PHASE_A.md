# Sprint 20.5 Phase A — Calculation Audit

Phase A verifies the mathematical path from sportsbook odds to dashboard EV.

## Checks

- American odds to decimal odds
- American odds to implied probability
- Model probability range
- Expected-value recomputation
- Stored versus calculated probability and EV
- Extreme model probabilities
- EV values above the existing 20% guardrail
- Eligibility outside the 2–20% EV guardrail
- Dashboard percentage scaling

## Outputs

- `data/audit/phase_a_calculation_audit.json`
- `data/audit/ev_trace_report.json`

## Interpretation

A formula mismatch is a hard failure. Suspicious but mathematically consistent values produce a warning so upstream probability quality can be corrected without confusing it with a display-format bug.

The initial repository evidence shows the dashboard multiplies decimal EV by 100 correctly. The unusually high average originates upstream: some records contain extreme model probabilities near 1.0, which create EV values above 100% at plus-money odds. Those records already fail the model's EV guardrail and are not eligible bets, but averaging every positive-EV record makes the dashboard headline misleading.

Phase A therefore separates:

- all-record average EV
- eligible-record average EV
- median EV
- formula correctness
- probability-quality warnings
