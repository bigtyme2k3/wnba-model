# Sprint 20.5 Phase B — Data Flow and Probability Source Audit

## Purpose

Trace the probability used by the edge database back to its exact source field and detect cases where confidence or scoring fields are treated as calibrated win probabilities.

## Current selection rule

`wnba_edge_database.py` uses the first available value in this order:

1. `simulation_probability`
2. `model_probability`
3. `probability`
4. `confidence`
5. `final_score`
6. `consensus_score`

The final three fields are score-like values. They may be useful for ranking, but they are unsafe as EV inputs unless independently calibrated and explicitly documented as probabilities.

## Audit checks

- Which probability candidate fields exist on each source record
- Which field wins the priority selection
- Whether the selected value matches the edge database value
- Whether confidence, final score, or consensus score was used as probability
- Selected probabilities at or above 95%
- Ambiguous source fields containing identical values
- Missing source-to-edge matches

## Data flow

`wnba_model_history.jsonl` → `wnba_edge_database.py:model_probability_for` → `wnba_edge_database.jsonl` → opportunity engines → professional dashboard

## Outputs

- `data/audit/phase_b_data_flow_audit.json`
- `data/audit/probability_source_trace.json`

## Interpretation

A Phase B warning does not mean the EV formula is wrong. It means the probability supplied to that formula may not be a calibrated probability. Phase C should use the Phase B evidence to restrict EV calculations to approved probability fields and introduce calibration diagnostics before altering model outputs.
