# Sprint 24 Phase 1 — Shadow Portfolio Governance

This phase converts the broad Sprint 23 shadow opportunity set into a smaller, disciplined research shortlist.

## Purpose

The raw Phase 3 scorer can produce hundreds of positive-EV rows. That is useful for discovery but not for controlled forward validation. Phase 1 applies uncertainty and exposure rules before an opportunity is placed on the research shortlist.

## Rules

- DraftKings and FanDuel only.
- Feature-ready rows only.
- Minimum estimated EV per $1: 0.03.
- Minimum model probability edge: 0.025.
- Maximum model-MAE-to-line ratio: 0.40.
- Keep the best listed offer for the same player, stat, side, and line.
- Maximum 20 opportunities total.
- Maximum 2 opportunities per player.
- Maximum 6 opportunities per game.
- Maximum 6 opportunities per stat category.

## Outputs

- `data/processed/sprint24/shadow_governed_shortlist.csv`
- `data/processed/sprint24/shadow_governance_audit.csv`
- `data/processed/sprint24/shadow_governance_catalog.json`

The audit file retains rejected and watch rows with their governance reason.

## Safety

This remains research-only and `SHADOW_ONLY`.

- Research stake is always 0 units.
- No production recommendation is changed.
- No bankroll allocation is produced.
- No model promotion is automatic.
- Forward-validation evidence remains required before any human promotion review.
