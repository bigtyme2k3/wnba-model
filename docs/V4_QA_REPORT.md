# WNBA V4 QA Report

Generated: `2026-07-20T15:35:11.949879+00:00`

**Overall:** YELLOW — 100.0/100

## Summary

- Modules: 25 green, 0 yellow, 0 red
- Dashboard JSON: 112 checked, 0 invalid, 3 empty
- Workflows: 40 checked, 1 high risk

## Module QA

| ID | Module | Declared | QA | Score | Owner |
|---|---|---:|---:|---:|---|
| M01 | Source Registry | active | green | 100 | `config/source_registry.json` |
| M02 | Schedule Core | active | green | 100 | `wnba_master_source_builder.py` |
| M03 | Odds Source Manager | active | green | 100 | `odds_source_manager.py` |
| M04 | Sportsbook Consensus | active | green | 100 | `wnba_sportsbook_consensus.py` |
| M05 | Player Stats Warehouse | active | green | 100 | `wnba_player_intelligence.py` |
| M06 | Boxscore Fallback | active | green | 100 | `wnba_stats_fallback_from_boxscores.py` |
| M07 | Play-by-Play Layer | active | green | 100 | `wnba_play_by_play_layer.py` |
| M08 | Matchup Intelligence | active | green | 100 | `wnba_matchup_intelligence.py` |
| M09 | Projection Engine | active | green | 100 | `wnba_projection_ai.py` |
| M10 | Player Props Model | active | green | 100 | `player_points.py` |
| M11 | Spread Model | active | green | 100 | `wnba_game_market_model.py` |
| M12 | Totals Model | active | green | 100 | `wnba_game_market_model.py` |
| M13 | Expected Value Engine | active | green | 100 | `wnba_decision_engine_final.py` |
| M14 | Portfolio Optimizer | active | green | 100 | `wnba_portfolio_optimizer_v2.py` |
| M15 | Risk Allocation | active | green | 100 | `wnba_risk_allocation.py` |
| M16 | CLV Tracker | active | green | 100 | `wnba_closing_line_tracker.py` |
| M17 | Results Grading | active | green | 100 | `wnba_results_grader.py` |
| M18 | Self Learning | active | green | 100 | `wnba_self_learning.py` |
| M19 | Model Explainability | active | green | 100 | `wnba_reasoning_layer.py` |
| M20 | Dashboard V4 | active | green | 100 | `patch_dashboard_navigation_v2.py` |
| M21 | Model Calibration | active | green | 100 | `wnba_model_calibration.py` |
| M22 | Feature Importance | active | green | 100 | `wnba_feature_importance.py` |
| M23 | Hyperparameter Optimization | active | green | 100 | `wnba_hyperparameter_optimizer.py` |
| M24 | Daily Retraining | active | green | 100 | `wnba_daily_retraining.py` |
| M25 | Ensemble Learning | active | green | 100 | `wnba_ensemble_learning.py` |

## Release blockers

- None detected by the static QA pass.

## Workflow risk

| Workflow | Steps | Continue-on-error | Ratio | Risk | Self-push |
|---|---:|---:|---:|---:|---:|
| `.github/workflows/bootstrap.yml` | 9 | 0 | 0.0 | low | True |
| `.github/workflows/daily_action_report_v2_extension.yml` | 9 | 0 | 0.0 | low | True |
| `.github/workflows/deepseek_master_prediction_extension.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/deepseek_portfolio_optimizer_extension.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/market_timing_extension.yml` | 9 | 0 | 0.0 | low | True |
| `.github/workflows/minutes_usage_extension.yml` | 9 | 0 | 0.0 | low | True |
| `.github/workflows/results_review_center_extension.yml` | 9 | 1 | 0.111 | low | True |
| `.github/workflows/results_tracker.yml` | 6 | 1 | 0.167 | low | True |
| `.github/workflows/v4_qa.yml` | 7 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_alt_market_watch.yml` | 12 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_alt_tab_repair.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_autonomous_agent.yml` | 11 | 5 | 0.455 | medium | False |
| `.github/workflows/wnba_betting_intelligence.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_closing_line_snapshots.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_controlled_recalibration.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_daily_ai_report.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_data_warehouse.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_full_game_performance.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_full_game_simulation.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_game_market_repair.yml` | 12 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_injury_refresh.yml` | 12 | 1 | 0.083 | low | True |
| `.github/workflows/wnba_intelligence_foundation.yml` | 52 | 27 | 0.519 | high | True |
| `.github/workflows/wnba_live_slate_refresh.yml` | 7 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_market_intelligence.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_mission_control.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_model_explainability.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_model_picks_ledger.yml` | 1 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_model_quality_guardrails.yml` | 10 | 2 | 0.2 | low | True |
| `.github/workflows/wnba_monte_carlo_live_test.yml` | 9 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_multi_source_fetch.yml` | 10 | 2 | 0.2 | low | True |
| `.github/workflows/wnba_odds_history_backfill.yml` | 7 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_odds_history_next_batch.yml` | 11 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_odds_history_repair_results.yml` | 6 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_player_props_history_repair.yml` | 9 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_postbuild_integrity.yml` | 10 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_postgame_learning_pipeline.yml` | 13 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_prop_card_calibration.yml` | 6 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_v4_player_props_audit.yml` | 4 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_v4_player_props_polish.yml` | 11 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_v4_status.yml` | 19 | 0 | 0.0 | low | False |
