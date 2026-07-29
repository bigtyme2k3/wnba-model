# WNBA V4 QA Report

Generated: `2026-07-29T15:37:38.422250+00:00`

**Overall:** YELLOW — 100.0/100

Operating context: `READY` — Pipeline ready for live model execution.

## Summary

- Modules: 25 green, 0 yellow, 0 red
- Dashboard JSON: 159 checked, 0 invalid, 0 expected empty, 4 unexpected empty
- Workflows: 106 checked, 0 high risk
- Forward validation: green

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

- None detected.

## Warnings

- Unexpected empty JSON: data/dashboard/wnba_alt_clv.json
- Unexpected empty JSON: data/dashboard/wnba_clv_summary.json
- Unexpected empty JSON: data/dashboard/wnba_portfolio_dashboard.json
- Unexpected empty JSON: data/dashboard/wnba_portfolio_optimizer_v2.json

## Workflow risk

| Workflow | Steps | Continue-on-error | Ratio | Critical masking | Risk |
|---|---:|---:|---:|---:|---:|
| `.github/workflows/bootstrap.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/daily_action_report_v2_extension.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/deepseek_master_prediction_extension.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/deepseek_portfolio_optimizer_extension.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/deploy_wnba_dashboard.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/market_timing_extension.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/minutes_usage_extension.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/results_review_center_extension.yml` | 9 | 1 | 0.111 | False | low |
| `.github/workflows/results_tracker.yml` | 6 | 1 | 0.167 | False | low |
| `.github/workflows/v4_qa.yml` | 8 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_active_slate_scanner.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_adaptive_confidence.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_alt_market_watch.yml` | 13 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_alt_tab_repair.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_automated_trend_discovery.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_autonomous_agent.yml` | 11 | 5 | 0.455 | False | medium |
| `.github/workflows/wnba_autonomous_pipeline.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_betting_intelligence.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_betting_intelligence_v2.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_closing_line_predictor.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_closing_line_snapshots.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_clv_intelligence.yml` | 8 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_confidence_calibration.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_controlled_recalibration.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_daily_ai_report.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_daily_edge_engine.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_daily_intelligence_brief.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_data_warehouse.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_ensemble_intelligence.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_entry_window_intelligence.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_forward_validation.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_full_game_performance.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_full_game_simulation.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_game_market_repair.yml` | 12 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_historical_prediction_reconstruction.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_injury_refresh.yml` | 12 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_intelligence_foundation.yml` | 15 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_legacy_player_schema_inspector.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_line_movement.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_live_prediction_tracker.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_live_result_grader.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_live_slate_refresh.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_market_enrichment.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_market_forecast_engine.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_market_intelligence.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_market_timeline.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_mission_control.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_model_audit.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_model_explainability.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_model_picks_ledger.yml` | 1 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_model_quality_guardrails.yml` | 10 | 2 | 0.2 | False | low |
| `.github/workflows/wnba_monte_carlo_live_test.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_monte_carlo_scenarios.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_multi_source_fetch.yml` | 11 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_odds_history_backfill.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_odds_history_next_batch.yml` | 11 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_odds_history_repair_results.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_odds_warehouse_v2.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_opportunity_scanner.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_player_prop_grading_bridge.yml` | 8 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_player_prop_intelligence.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_player_props_history_repair.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_postbuild_integrity.yml` | 10 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_postgame_learning_pipeline.yml` | 13 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_production_readiness.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_prop_card_calibration.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_remaining_season_intelligence.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_signal_performance_engine.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sportsbook_leader_intelligence.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sportsbook_leader_normalization.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint17_live_test.yml` | 8 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint19_edge_database.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint19_phase2_clv.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_5_phase_a_calculation_audit.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_5_phase_b_data_flow_audit.yml` | 4 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_5_phase_c_calibration_audit.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_5_phase_d_calibration_validation.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_5_phase_e_ranking_market_validation.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_phase1_line_shopping.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_phase2_opportunity_ranking.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_phase3_market_movement.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_phase4_opportunity_finder.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint20_phase5_professional_dashboard.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint21_phase1_feature_signal_audit.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint21_phase2_feature_set_validation.yml` | 5 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint21_phase3_model_rebuild.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint22_legacy_player_recovery.yml` | 6 | 1 | 0.167 | False | low |
| `.github/workflows/wnba_sprint22_phase1_warehouse_expansion.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint22_phase2_1_player_ingestion.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint22_phase2_2_historical_player_backfill.yml` | 14 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint22_phase2_player_intelligence.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint23_phase1_player_features.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint23_phase2_props_integration.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint23_phase3_market_opportunities.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint23_phase4_shadow_validation.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint23_phase5_explainable_shadow.yml` | 10 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint24_phase1_shadow_governance.yml` | 9 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_sprint24_phase2_live_market_integration.yml` | 11 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_steam_sharp.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_trend_outcome_validation.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_v4_player_props_audit.yml` | 4 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_v4_player_props_polish.yml` | 20 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_v4_status.yml` | 19 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_validation_dashboard.yml` | 7 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_validation_performance_analytics.yml` | 6 | 0 | 0.0 | False | low |
| `.github/workflows/wnba_warehouse_migration.yml` | 9 | 0 | 0.0 | False | low |
