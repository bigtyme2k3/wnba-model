# Dashboard Tab Dependency Map

## Build chain

- `build_dashboard_v4.py`
- `patch_dashboard_v4_games_markets.py`
- `patch_dashboard_v4_consistency.py`
- `patch_dashboard_v4_live_slate.py`
- `patch_dashboard_v4_portfolio_ai.py`
- `patch_dashboard_navigation_v2.py`

## Tab ownership

### Games
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_consistency.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_live_slate.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### Game Performance
- Status: **mapped**
- Renderers: `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: None found
- Risk flags: None detected

### Game Props
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_consistency.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_live_slate.py`, `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### Player Props
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_consistency.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_live_slate.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### ALT Streaks
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### ALT Performance
- Status: **unmapped**
- Renderers: None found
- JSON sources: None found
- Risk flags: None detected

### Daily Edges
- Status: **mapped**
- Renderers: `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_master.json`
- Risk flags: missing_model_placeholder

### Ensemble
- Status: **unmapped**
- Renderers: None found
- JSON sources: None found
- Risk flags: None detected

### Simulation
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### Best Bets
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_consistency.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_live_slate.py`, `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### Portfolio
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### AI Center
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_consistency.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_live_slate.py`, `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### Results
- Status: **mapped**
- Renderers: `build_dashboard_v4.py`, `patch_dashboard_navigation_v2.py`, `patch_dashboard_v4_games_markets.py`, `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: `data/dashboard/wnba_ai_coach.json`, `data/dashboard/wnba_autonomous_agent.json`, `data/dashboard/wnba_consensus_engine.json`, `data/dashboard/wnba_cross_market_top_plays.json`, `data/dashboard/wnba_decision_engine_final.json`, `data/dashboard/wnba_game_market_model.json`, `data/dashboard/wnba_market_engine.json`, `data/dashboard/wnba_master.json`, `data/dashboard/wnba_matchup_intelligence.json`, `data/dashboard/wnba_monte_carlo_engine.json`, `data/dashboard/wnba_odds_health.json`, `data/dashboard/wnba_portfolio_dashboard.json`, `data/dashboard/wnba_projection_ai.json`, `data/dashboard/wnba_results_grading.json`, `data/dashboard/wnba_risk_allocation.json`, `data/dashboard/wnba_self_learning.json`, `data/dashboard/wnba_source_health.json`, `data/dashboard/wnba_sportsbook_consensus.json`, `data/dashboard/wnba_stats_quality.json`, `data/dashboard/wnba_unified_player_simulation_v2.json`, `data/dashboard/wnba_v4_status.json`
- Risk flags: missing_model_placeholder, silent_json_fallback, synthetic_history_generator, team_guess_from_player_name

### Performance
- Status: **mapped**
- Renderers: `patch_dashboard_v4_portfolio_ai.py`
- JSON sources: None found
- Risk flags: None detected

## Immediate blockers

- `build_dashboard_v4.py` — **team_guess_from_player_name**
- `build_dashboard_v4.py` — **synthetic_history_generator**
- `build_dashboard_v4.py` — **silent_json_fallback**
- `patch_dashboard_v4_games_markets.py` — **missing_model_placeholder**
- `patch_dashboard_navigation_v2.py` — **synthetic_history_generator**
