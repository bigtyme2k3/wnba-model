# Sprint 22 Phase 2.2 — Historical Player Backfill

## Objective

Populate the player intelligence warehouse across a configurable historical season range using the existing Sportsdataverse/ESPN collector and the Phase 2.1 normalization bridge.

## Workflow

`WNBA Sprint 22 Phase 2.2 Historical Player Backfill`

Inputs:

- `start_season` — defaults to 2015
- `end_season` — defaults to 2025
- `collect_current` — optionally adds the current ESPN season

The workflow:

1. downloads historical `wehoop_player_box_<season>.csv` files;
2. optionally collects the current season from ESPN;
3. normalizes each season into `player_game_logs_<season>.csv` and `player_profiles_<season>.csv`;
4. rebuilds the Sprint 22 Phase 2 warehouse;
5. audits historical coverage and duplicate player-game keys;
6. commits raw normalized inputs and warehouse artifacts.

## New output

- `data/warehouse/sprint22/player/historical_backfill_catalog.json`

The catalog reports season coverage, row counts, unique players, date ranges, duplicate player-game keys, missing dates, and final warehouse table sizes.

## Deployment gate

The backfill passes only when:

- every requested historical season produced a normalized game-log file;
- player-game keys are unique;
- player profiles are populated;
- player game logs are populated;
- leakage-safe rolling metrics are populated.

A missing requested season causes the workflow to stop rather than silently claiming a complete backfill.

## Safety

This phase does not modify production probabilities, EV calculations, model deployment, or betting recommendations. It only expands and validates historical player data.
