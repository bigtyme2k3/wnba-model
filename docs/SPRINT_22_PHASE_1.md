# Sprint 22 Phase 1 — Warehouse Expansion

## Objective

Convert the repository's existing raw WNBA files into stable, AI-friendly warehouse layers before adding new external sources.

## Layers

- `team_season.csv` — team traditional and advanced season statistics
- `player_season.csv` — player traditional and advanced season statistics
- `game_context.csv` — schedules, results and game identifiers
- `market_snapshot.csv` — sportsbook and consensus market observations
- `warehouse_catalog.json` — provenance, row counts, keys, coverage and ingestion errors

## Design rules

- Raw source files remain unchanged.
- Column names are normalized to snake case.
- Every row retains `source_file` and `source_system` provenance.
- Season is inferred from filenames when missing.
- Dates are normalized where possible.
- Empty layers are valid and reported as zero-row layers rather than causing the workflow to fail.
- This phase does not alter production models, probabilities or betting recommendations.

## Existing source patterns

The builder discovers the files already produced by the project:

- `team_advanced_*.csv`, `team_stats_*.csv`
- `player_advanced_*.csv`, `player_stats_*.csv`
- `schedule_*.csv`, `game_logs_*.csv`, `scores_*.csv`
- `odds_*.csv`, `odds_consensus.csv`, `odds_historical.csv`

## Next source priorities

The catalog records the next high-value additions:

1. injuries and player availability
2. starting lineups and rotation continuity
3. play-by-play and lineup-derived metrics
4. referee assignments
5. exact travel distance and time-zone changes

Phase 2 will expand historical market snapshots and preserve opening-to-closing movement without future-data leakage.
