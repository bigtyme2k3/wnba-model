# WNBA V4 QA Report

Generated: `2026-07-12T16:53:13.428192+00:00`

**Overall:** YELLOW — 100.0/100

## Summary

- Modules: 25 green, 0 yellow, 0 red
- Dashboard JSON: 51 checked, 0 invalid, 2 empty
- Workflows: 23 checked, 1 high risk

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
| M16 | CLV Tracker | partial | green | 100 | `wnba_closing_line_tracker.py` |
| M17 | Results Grading | partial | green | 100 | `wnba_results_grader.py` |
| M18 | Self Learning | partial | green | 100 | `wnba_self_learning.py` |
| M19 | Model Explainability | partial | green | 100 | `wnba_reasoning_layer.py` |
| M20 | Dashboard V4 | active | green | 100 | `patch_dashboard_navigation_v2.py` |
| M21 | Model Calibration | planned | green | 100 | `wnba_v4_status_engine.py` |
| M22 | Feature Importance | planned | green | 100 | `wnba_v4_status_engine.py` |
| M23 | Hyperparameter Optimization | planned | green | 100 | `wnba_v4_status_engine.py` |
| M24 | Daily Retraining | planned | green | 100 | `wnba_self_learning.py` |
| M25 | Ensemble Learning | planned | green | 100 | `wnba_v4_status_engine.py` |

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
| `.github/workflows/wnba_autonomous_agent.yml` | 11 | 5 | 0.455 | medium | False |
| `.github/workflows/wnba_closing_line_snapshots.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_data_warehouse.yml` | 5 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_injury_refresh.yml` | 12 | 1 | 0.083 | low | True |
| `.github/workflows/wnba_intelligence_foundation.yml` | 52 | 27 | 0.519 | high | True |
| `.github/workflows/wnba_model_quality_guardrails.yml` | 10 | 2 | 0.2 | low | True |
| `.github/workflows/wnba_monte_carlo_live_test.yml` | 9 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_multi_source_fetch.yml` | 10 | 2 | 0.2 | low | True |
| `.github/workflows/wnba_phase5_learning.yml` | 14 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_postbuild_integrity.yml` | 10 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_v4_player_props_audit.yml` | 4 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_v4_player_props_polish.yml` | 11 | 0 | 0.0 | low | True |
| `.github/workflows/wnba_v4_status.yml` | 22 | 0 | 0.0 | low | False |
| `.github/workflows/wnba_v4_terminal_cleanup.yml` | 8 | 0 | 0.0 | low | True |
