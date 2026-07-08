# WNBA Model Architecture

## Current direction

The project is moving away from many dashboard-specific files and toward one clean data flow:

```text
External sources
  -> source adapters
  -> normalized master database
  -> model engines
  -> dashboard
```

The dashboard should not read random raw files directly. It should read the normalized master payload first, then fall back only when the master payload is unavailable.

## Source-of-truth plan

| Layer | Primary source | Backup | Reliance |
|---|---|---|---|
| Games / schedule / teams | SportsDataverse | scores CSV / sportsbook consensus | High |
| Player and team stats | nba_api / official stats | boxscore warehouse fallback | High |
| Historical game logs | local boxscore warehouse | SportsDataverse historical data | Very high |
| Odds / props | local odds pipeline + sportsbook consensus | The Odds API only when needed | Very high |
| AI reasoning | current JSON engines | LiteLLM planned | Medium |
| Model tuning | fixed weights today | Optuna planned | Medium |

## Active files going forward

Core source layer:

- `config/source_registry.json`
- `wnba_master_source_builder.py`
- `data/master/wnba_master.json`
- `data/dashboard/wnba_master.json`
- `data/dashboard/wnba_master_source_health.json`

Core odds layer:

- `odds_source_manager.py`
- `wnba_live_odds_layer.py`
- `wnba_sportsbook_consensus.py`
- `wnba_odds_health.py`

Core stats layer:

- `scrape_wnba_stats.py`
- `wnba_stats_fallback_from_boxscores.py`
- `wnba_stats_quality.py`
- `wnba_player_intelligence.py`

Core model layer:

- `wnba_matchup_intelligence.py`
- `wnba_consensus_engine.py`
- `wnba_monte_carlo_engine.py`
- `wnba_projection_ai.py`
- `wnba_market_engine.py`
- `wnba_decision_engine_final.py`
- `wnba_portfolio_optimizer_v2.py`
- `wnba_risk_allocation.py`
- `wnba_ai_coach.py`

Core presentation layer:

- `patch_dashboard_navigation_v2.py`
- `docs/index.html`

## Cleanup rule

Do not delete old experimental modules until the master database has replaced them. Mark them legacy and stop wiring them into workflows first. Delete only after the new path is stable.
