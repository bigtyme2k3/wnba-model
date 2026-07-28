# Sprint 22 Phase 2.1 — Player Data Ingestion

## Purpose

Populate the Sprint 22 player warehouse using the repository's existing `collect_wehoop.py` collector.

The existing collector writes player box scores as `wehoop_player_box_<season>.csv`. Phase 2 expects normalized `player_game_logs_<season>.csv` and `player_profiles_<season>.csv` inputs. This phase provides the bridge between those layers.

## Pipeline

1. Download historical Sportsdataverse player box scores.
2. Download current-season ESPN player box scores.
3. Normalize both schemas into one player-game format.
4. Preserve source-issued player IDs where available.
5. Remove duplicate player-game rows.
6. Derive season-level profile records.
7. Run the Sprint 22 Phase 2 warehouse builder.
8. Verify that profile, game-log, and rolling-metric tables are populated.

## Outputs

- `data/raw/player_game_logs_<season>.csv`
- `data/raw/player_profiles_<season>.csv`
- `data/raw/player_ingestion_catalog.json`
- refreshed `data/warehouse/sprint22/player/` tables

## Workflow

Run **WNBA Sprint 22 Phase 2.1 Player Ingestion** manually. Historical start/end seasons and current-season collection can be selected from the workflow form.

## Safety

The workflow fails verification when no player game logs are collected. It does not fabricate player data, and it leaves production predictions and betting recommendations unchanged.
