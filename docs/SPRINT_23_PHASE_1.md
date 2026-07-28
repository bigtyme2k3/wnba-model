# Sprint 23 Phase 1 — Player Feature Engine

Builds model-ready, leakage-safe features from the verified Sprint 22 player warehouse.

## Outputs

- `data/features/sprint23/player/player_game_features.csv`
- `data/features/sprint23/player/player_latest_features.csv`
- `data/features/sprint23/player/player_feature_catalog.json`

## Feature groups

- Pregame rolling averages and volatility over 3, 5, and 10 games
- Season-to-date averages
- PRA rolling averages
- Minutes and points trends
- Rest days, back-to-backs, and long-rest flags
- Historical player-versus-opponent averages
- Latest availability status and risk flag
- Feature-readiness flag after three prior games

All rolling and expanding statistics use `shift(1)` so the current game's result is never included in its own features. Only seasons listed in `player_coverage_manifest.json` are accepted.

## Run

GitHub Actions → **WNBA Sprint 23 Phase 1 Player Feature Engine** → Run workflow.
