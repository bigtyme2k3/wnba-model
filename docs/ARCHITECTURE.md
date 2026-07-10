# WNBA Model Architecture

## Current direction

The project uses one clean data flow:

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
| Games / schedule / teams | SportsDataverse `wehoop` / ESPN | sports-skills scoreboard and committed score CSVs | High |
| Player and team stats | SportsDataverse `wehoop` / ESPN boxscores | local boxscore warehouse fallback | Very high |
| Historical game logs | local wehoop boxscore warehouse | committed boxscore CSVs | Very high |
| Odds / props | The Odds API and normalized sportsbook consensus | cached/manual odds | Very high |
| AI reasoning | current JSON engines | LiteLLM planned | Medium |
| Model tuning | fixed weights today | Optuna planned | Medium |

`stats.wnba.com` is retired and is not part of any active workflow.

## Active files going forward

Core source layer:

- `fetch_wehoop_stats.R`
- `config/source_registry.json`
- `wnba_master_source_builder.py`
- `data/master/wnba_master.json`
- `data/dashboard/wnba_master.json`
- `data/dashboard/wnba_master_source_health.json`

Core odds layer:

- `scrape_odds.py`
- `scrape_odds_props.py`
- `line_shopping.py`
- `odds_source_manager.py`
- `wnba_live_odds_layer.py`
- `wnba_sportsbook_consensus.py`
- `wnba_odds_health.py`

Core stats layer:

- `fetch_wehoop_stats.R`
- `data/raw/wehoop_player_boxscores.csv`
- `data/raw/boxscores_wehoop.csv`
- `data/raw/wnba_players_live.json`
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

- `build_dashboard_v4.py`
- `patch_dashboard_v4_player_props_polish.py`
- `docs/index.html`

## Daily workflow

```text
WNBA Multi-Source Data Fetch
  -> wehoop schedule, player boxscores, player stats
  -> sports-skills supplemental schedule/injuries/standings

WNBA Intelligence Foundation
  -> The Odds API odds and props
  -> current wehoop statistics
  -> projections, best bets, dashboard

WNBA Results Tracker
  -> grading, performance, learning
```

## Cleanup rule

Only one active workflow should own each major stage. Legacy overlapping workflows should be removed after the replacement path is active and verified.
