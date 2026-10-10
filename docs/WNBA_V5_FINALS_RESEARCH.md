# WNBA V5 Finals matchup research — 2026

This is a **research-only** report. It does not alter production predictions, archived decisions, confidence thresholds, or wagers.

## Reproducible evidence

Run `python scripts/wnba_finals_research.py` from the repository root. The script reads the persisted graded game-performance archive, selects 2026 postseason games featuring either Finals participant, and writes `data/dashboard/wnba_finals_research.json`. Only **GRADED** games with recorded final scores are used. Sample sizes and cutoffs are displayed; no market odds or future predictions are manufactured.

## Research protocol

- Compare Atlanta Dream and Golden State Valkyries on playoff win rate, points for/against, point differential, winner-prediction accuracy, signed margin error and total error.
- Evaluate each club's most recent three graded playoff games separately, without claiming they represent a full-season estimate.
- Keep Game 1 predictions in shadow until an actual dated Finals slate, verified injury context, and approved-book market lines are available.
- Preserve `config/wnba_playoff_mode.json` betting gates. Never use this research report to auto-promote PASS into BET.
- A prior-round result is not an independent Finals matchup observation. Do not backfill the Finals series with hypothetical outcomes.
