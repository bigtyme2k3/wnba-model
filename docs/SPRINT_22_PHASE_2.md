# Sprint 22 Phase 2 — Player Intelligence Warehouse

## Objective

Populate a stable player-level warehouse from the repository's existing player season, game-log, and availability sources.

## Outputs

- `data/warehouse/sprint22/player/player_profile.csv`
- `data/warehouse/sprint22/player/player_game_logs.csv`
- `data/warehouse/sprint22/player/player_rolling_metrics.csv`
- `data/warehouse/sprint22/player/player_availability.csv`
- `data/warehouse/sprint22/player/player_matchups.csv`
- `data/warehouse/sprint22/player/player_catalog.json`

## Source discovery

The builder automatically scans `data/raw` for:

- player season/profile files: `player_stats_*`, `player_advanced_*`, `players_*`, `roster_*`
- player game logs: `player_game_logs_*`, `player_gamelogs_*`, `boxscores_players_*`, `player_boxscores_*`
- availability files: `injuries_*`, `player_availability_*`, `inactive_*`

Missing game-log or availability sources produce valid empty tables and a catalog note rather than a workflow failure.

## Stable identity

Every player receives a deterministic `player_id` derived from normalized player and team values. Game logs also receive a deterministic `game_id` from date, team, and opponent. These keys remove dependence on inconsistent display names.

## Rolling metrics

Rolling 3-, 5-, and 10-game metrics are calculated with `shift(1)`. The current game's result is never included in its own pregame rolling values. Supported rolling statistics include minutes, points, rebounds, assists, steals, blocks, and turnovers when present.

## Matchup and availability layers

The matchup table summarizes historical player performance by opponent. The availability table normalizes injury or status snapshots when source files exist.

## Validation

QA verifies:

- stable and unique player IDs
- unique player-game keys
- profile coalescing across traditional and advanced files
- leakage-safe rolling calculations
- matchup aggregation
- availability normalization
- catalog and output-table integrity

This phase does not change production predictions, probabilities, EV calculations, or recommendations.
