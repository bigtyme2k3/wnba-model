# WNBA Warehouse Health Report

Generated: `2026-08-01T17:16:27.786356+00:00`
Expected target date: `2026-08-01`
Overall status: **YELLOW**

## Summary

- **Files:** 290
- **Green:** 258
- **Yellow:** 32
- **Red:** 0
- **Duplicate Names:** 106

## Dataset Status

| Status | Group | Path | Target date | Findings |
|---|---|---|---|---|
| YELLOW | dashboard | `data/dashboard/daily_action_report_v2.json` | 2026-07-10 | target_date_mismatch:2026-07-10!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/deepseek_portfolio_optimizer.json` | 2026-07-08 | target_date_mismatch:2026-07-08!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/market_intelligence.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/market_movement.json` | 2026-08-01 | None |
| YELLOW | dashboard | `data/dashboard/market_timing_intelligence.json` | 2026-07-10 | target_date_mismatch:2026-07-10!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/master_feed.json` | 2026-07-09 | target_date_mismatch:2026-07-09!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/minutes_usage_intelligence.json` | 2026-07-10 | target_date_mismatch:2026-07-10!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/opportunity_finder.json` | 2026-07-27 | target_date_mismatch:2026-07-27!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/professional_dashboard.json` | 2026-07-27 | target_date_mismatch:2026-07-27!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/projection_accuracy.json` | 2026-07-09 | target_date_mismatch:2026-07-09!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/projection_intelligence_v2.json` | 2026-07-09 | target_date_mismatch:2026-07-09!=2026-08-01 |
| YELLOW | dashboard | `data/dashboard/results_review_center.json` | 2026-07-08 | target_date_mismatch:2026-07-08!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/sprint23_shadow_intelligence.json` | None | None |
| GREEN | dashboard | `data/dashboard/terminal_ui.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_adaptive_confidence.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_ai_coach.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_archive_reconciliation.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_clv.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_exception_packet.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_game_mapping_repair.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_market_warehouse.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_market_watch_due.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_matchup_mapping_repair.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_performance.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_performance_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_schedule_mapping_repair.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_alt_streaks.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_ancillary_projection_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_ancillary_projection_v2_acceptance.json` | None | None |
| YELLOW | dashboard | `data/dashboard/wnba_autonomous_agent.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_autonomous_pipeline.json` | 2026-08-01 | None |
| YELLOW | dashboard | `data/dashboard/wnba_backtest_engine.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_betting_intelligence.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_betting_ledger_summary.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_betting_validation.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_closing_line_predictor_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_clv_edge_report.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_clv_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_confidence_calibration.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_consensus_engine.json` | 2026-08-01 | None |
| YELLOW | dashboard | `data/dashboard/wnba_context_engine.json` | 2026-07-09 | target_date_mismatch:2026-07-09!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_cross_market_top_plays.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_cross_market_top_plays_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_daily_ai_report.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_daily_edges.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_daily_intelligence_brief.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_daily_retraining.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_dashboard_tab_qa.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_data_lineage.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_data_warehouse.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_decision_engine_final.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_edge_database.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_ensemble_intelligence.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_ensemble_learning.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_entry_window_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_feature_importance.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_final_qa.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_forward_validation.json` | None | None |
| YELLOW | dashboard | `data/dashboard/wnba_full_game_performance.json` | 2026-07-13 | target_date_mismatch:2026-07-13!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_full_game_performance_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_full_game_simulation_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_game_market_model.json` | 2026-08-01 | None |
| YELLOW | dashboard | `data/dashboard/wnba_game_predictions.json` | 2026-07-21 | target_date_mismatch:2026-07-21!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_game_predictions_ledger.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_game_props_q1.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_historical_prediction_reconstruction.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_historical_summary.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_hyperparameter_optimizer.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_injury_intelligence.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_line_movement_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_live_games.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_live_odds_layer.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_live_performance_analytics_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_live_prediction_tracker_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_live_result_grader_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_live_results_engine.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_live_scanner_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_live_slate_status.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_market_engine.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_market_enrichment_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_market_forecast_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_market_intelligence.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_market_intelligence_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_market_timeline_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_master.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_master_database_summary.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_master_source_health.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_matchup_intelligence.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_minutes_projection_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_minutes_projection_v2_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_mission_control.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_mission_control_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_model_audit.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_model_calibration.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_model_explainability.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_model_explainability_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_model_picks_ledger.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_model_picks_ledger_acceptance.json` | None | None |
| YELLOW | dashboard | `data/dashboard/wnba_model_quality_audit.json` | 2026-07-10 | target_date_mismatch:2026-07-10!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_monte_carlo_engine.json` | 2026-08-01 | None |
| YELLOW | dashboard | `data/dashboard/wnba_monte_carlo_live_test.json` | 2026-07-22 | target_date_mismatch:2026-07-22!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_monte_carlo_scenarios.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_odds_health.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_odds_history_dashboard.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_odds_history_outcomes.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_odds_history_results.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_odds_history_trends.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_opponent_stat_rankings.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_opportunity_rankings.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_opportunity_scanner_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_pace_minutes_opponent_rankings.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_parlay_optimizer_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_parlay_optimizer_v2_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_phase5_backtest.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_phase5_learning.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_pipeline_readiness.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_play_by_play_layer.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_player_game_log_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_player_game_logs.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_player_intelligence.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_player_prop_grading_bridge.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_player_prop_intelligence.json` | None | None |
| YELLOW | dashboard | `data/dashboard/wnba_player_props_history_repair.json` | 2026-07-17 | target_date_mismatch:2026-07-17!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_points_projection_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_points_projection_v2_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_portfolio_dashboard.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_portfolio_optimizer_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_position_opponent_rankings.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_production_readiness.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_projection_ai.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_projection_performance.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_projection_performance_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_prop_bet_cards.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_prop_card_performance.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_q1_team_history.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_reasoning_layer.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_rebounds_assists_projection_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_rebounds_assists_projection_v2_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_remaining_season_intelligence.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_results_grading.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_risk_allocation.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_self_learning.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_signal_performance_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_source_health.json` | 2026-08-01 | None |
| YELLOW | dashboard | `data/dashboard/wnba_source_shopping.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_sportsbook_consensus.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_sportsbook_leader_normalized_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_sportsbook_leader_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_standings.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_stats_quality.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_steam_sharp_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_trend_discovery_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_trend_outcome_validation_summary.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_trend_research.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_unified_player_simulation_v2.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_unified_player_simulation_v2_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_feedback_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_foundation_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_intelligence_acceptance.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_output_qa.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_player_props_audit.json` | 2026-08-01 | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_qa.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v4_status.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v5_model_intelligence.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v5_player_profiles.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_v5_sportsbook_intelligence.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_validation_dashboard.json` | None | None |
| GREEN | dashboard | `data/dashboard/wnba_validation_dashboard_summary.json` | None | None |
| YELLOW | dashboard | `data/dashboard/wnba_vote_layer_v2.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | dashboard | `data/dashboard/wnba_warehouse_health.json` | None | None |
| GREEN | master | `data/master/wnba_master.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/market_intelligence.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/market_movement.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/opportunity_finder.json` | 2026-07-27 | target_date_mismatch:2026-07-27!=2026-08-01 |
| YELLOW | warehouse | `data/warehouse/professional_dashboard.json` | 2026-07-27 | target_date_mismatch:2026-07-27!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/sports_skills_provider_status.json` | None | None |
| GREEN | warehouse | `data/warehouse/sprint24_phase2_live_market_catalog.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_adaptive_confidence.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_ai_coach.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_archive_reconciliation.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_clv.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_exception_packet.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_game_mapping_repair.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_market_warehouse.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_matchup_mapping_repair.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_performance.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_schedule_mapping_repair.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_alt_streaks.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_ancillary_projection_v2.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_autonomous_agent.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_autonomous_pipeline.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_backtest_engine.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_betting_intelligence.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_betting_ledger_summary.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_calibration_deployment_policy.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_clv_edge_report.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_clv_summary.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_confidence_calibration.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_consensus_engine.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_cross_market_top_plays.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_daily_ai_report.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_daily_edges.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_daily_retraining.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_data_lineage.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_decision_engine_final.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_edge_database.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_ensemble_intelligence.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_ensemble_learning.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_feature_importance.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_final_qa.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_forward_validation.json` | None | None |
| YELLOW | warehouse | `data/warehouse/wnba_full_game_performance.json` | 2026-07-13 | target_date_mismatch:2026-07-13!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_full_game_simulation_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_futures.json` |  | None |
| GREEN | warehouse | `data/warehouse/wnba_game_market_model.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_game_predictions.json` | 2026-07-21 | target_date_mismatch:2026-07-21!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_game_predictions_ledger.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_game_props_q1.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_games.json` |  | empty_payload |
| GREEN | warehouse | `data/warehouse/wnba_historical_prediction_reconstruction.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_historical_summary.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_hyperparameter_optimizer.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_injuries.json` |  | empty_payload |
| GREEN | warehouse | `data/warehouse/wnba_injury_intelligence.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_live_odds_layer.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_live_results_engine.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_live_slate_status.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_market_engine.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_market_intelligence.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_master_database_summary.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_matchup_intelligence.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_minutes_projection_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_mission_control.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_model_audit.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_model_calibration.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_model_explainability.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_model_picks_ledger.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_model_quality_audit.json` | 2026-07-10 | target_date_mismatch:2026-07-10!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_monte_carlo_engine.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_monte_carlo_scenarios.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_odds_health.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_history_backfill_plan.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_history_dashboard.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_history_outcomes.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_history_results.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_history_summary.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_history_trends.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_warehouse_v2_intelligence.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_odds_warehouse_v2_summary.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_opponent_stat_rankings.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_opportunity_rankings.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_pace_minutes_opponent_rankings.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_parlay_optimizer_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_phase5_backtest.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_phase5_learning.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_pipeline_readiness.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_play_by_play_layer.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_player_game_logs.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_player_intelligence.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_player_prop_grading_bridge.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_player_prop_intelligence.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_points_projection_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_portfolio_dashboard.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_portfolio_optimizer_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_position_opponent_rankings.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_probability_calibrator.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_production_readiness.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_projection_ai.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_projection_performance.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_prop_bet_cards.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_prop_card_performance.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_q1_team_history.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_reasoning_layer.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_rebounds_assists_projection_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_results_grading.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_risk_allocation.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_self_learning.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_source_health.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_source_quality.json` | 2026-08-01 | None |
| YELLOW | warehouse | `data/warehouse/wnba_source_shopping.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_sportsbook_consensus.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_standings.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_stats_quality.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_unified_player_simulation_v2.json` | 2026-08-01 | None |
| GREEN | warehouse | `data/warehouse/wnba_v5_model_intelligence.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_v5_player_profiles.json` | None | None |
| GREEN | warehouse | `data/warehouse/wnba_v5_sportsbook_intelligence.json` | None | None |
| YELLOW | warehouse | `data/warehouse/wnba_vote_layer_v2.json` | 2026-07-31 | target_date_mismatch:2026-07-31!=2026-08-01 |
| GREEN | warehouse | `data/warehouse/wnba_warehouse_migration_report.json` | None | None |

## Duplicate Dataset Names

- `market_intelligence.json`: data/dashboard/market_intelligence.json, data/warehouse/market_intelligence.json
- `market_movement.json`: data/dashboard/market_movement.json, data/warehouse/market_movement.json
- `opportunity_finder.json`: data/dashboard/opportunity_finder.json, data/warehouse/opportunity_finder.json
- `professional_dashboard.json`: data/dashboard/professional_dashboard.json, data/warehouse/professional_dashboard.json
- `wnba_adaptive_confidence.json`: data/dashboard/wnba_adaptive_confidence.json, data/warehouse/wnba_adaptive_confidence.json
- `wnba_ai_coach.json`: data/dashboard/wnba_ai_coach.json, data/warehouse/wnba_ai_coach.json
- `wnba_alt_archive_reconciliation.json`: data/dashboard/wnba_alt_archive_reconciliation.json, data/warehouse/wnba_alt_archive_reconciliation.json
- `wnba_alt_clv.json`: data/dashboard/wnba_alt_clv.json, data/warehouse/wnba_alt_clv.json
- `wnba_alt_exception_packet.json`: data/dashboard/wnba_alt_exception_packet.json, data/warehouse/wnba_alt_exception_packet.json
- `wnba_alt_game_mapping_repair.json`: data/dashboard/wnba_alt_game_mapping_repair.json, data/warehouse/wnba_alt_game_mapping_repair.json
- `wnba_alt_market_warehouse.json`: data/dashboard/wnba_alt_market_warehouse.json, data/warehouse/wnba_alt_market_warehouse.json
- `wnba_alt_matchup_mapping_repair.json`: data/dashboard/wnba_alt_matchup_mapping_repair.json, data/warehouse/wnba_alt_matchup_mapping_repair.json
- `wnba_alt_performance.json`: data/dashboard/wnba_alt_performance.json, data/warehouse/wnba_alt_performance.json
- `wnba_alt_schedule_mapping_repair.json`: data/dashboard/wnba_alt_schedule_mapping_repair.json, data/warehouse/wnba_alt_schedule_mapping_repair.json
- `wnba_alt_streaks.json`: data/dashboard/wnba_alt_streaks.json, data/warehouse/wnba_alt_streaks.json
- `wnba_ancillary_projection_v2.json`: data/dashboard/wnba_ancillary_projection_v2.json, data/warehouse/wnba_ancillary_projection_v2.json
- `wnba_autonomous_agent.json`: data/dashboard/wnba_autonomous_agent.json, data/warehouse/wnba_autonomous_agent.json
- `wnba_autonomous_pipeline.json`: data/dashboard/wnba_autonomous_pipeline.json, data/warehouse/wnba_autonomous_pipeline.json
- `wnba_backtest_engine.json`: data/dashboard/wnba_backtest_engine.json, data/warehouse/wnba_backtest_engine.json
- `wnba_betting_intelligence.json`: data/dashboard/wnba_betting_intelligence.json, data/warehouse/wnba_betting_intelligence.json
- `wnba_betting_ledger_summary.json`: data/dashboard/wnba_betting_ledger_summary.json, data/warehouse/wnba_betting_ledger_summary.json
- `wnba_clv_edge_report.json`: data/dashboard/wnba_clv_edge_report.json, data/warehouse/wnba_clv_edge_report.json
- `wnba_clv_summary.json`: data/dashboard/wnba_clv_summary.json, data/warehouse/wnba_clv_summary.json
- `wnba_confidence_calibration.json`: data/dashboard/wnba_confidence_calibration.json, data/warehouse/wnba_confidence_calibration.json
- `wnba_consensus_engine.json`: data/dashboard/wnba_consensus_engine.json, data/warehouse/wnba_consensus_engine.json
- `wnba_cross_market_top_plays.json`: data/dashboard/wnba_cross_market_top_plays.json, data/warehouse/wnba_cross_market_top_plays.json
- `wnba_daily_ai_report.json`: data/dashboard/wnba_daily_ai_report.json, data/warehouse/wnba_daily_ai_report.json
- `wnba_daily_edges.json`: data/dashboard/wnba_daily_edges.json, data/warehouse/wnba_daily_edges.json
- `wnba_daily_retraining.json`: data/dashboard/wnba_daily_retraining.json, data/warehouse/wnba_daily_retraining.json
- `wnba_data_lineage.json`: data/dashboard/wnba_data_lineage.json, data/warehouse/wnba_data_lineage.json
- `wnba_decision_engine_final.json`: data/dashboard/wnba_decision_engine_final.json, data/warehouse/wnba_decision_engine_final.json
- `wnba_edge_database.json`: data/dashboard/wnba_edge_database.json, data/warehouse/wnba_edge_database.json
- `wnba_ensemble_intelligence.json`: data/dashboard/wnba_ensemble_intelligence.json, data/warehouse/wnba_ensemble_intelligence.json
- `wnba_ensemble_learning.json`: data/dashboard/wnba_ensemble_learning.json, data/warehouse/wnba_ensemble_learning.json
- `wnba_feature_importance.json`: data/dashboard/wnba_feature_importance.json, data/warehouse/wnba_feature_importance.json
- `wnba_final_qa.json`: data/dashboard/wnba_final_qa.json, data/warehouse/wnba_final_qa.json
- `wnba_forward_validation.json`: data/dashboard/wnba_forward_validation.json, data/warehouse/wnba_forward_validation.json
- `wnba_full_game_performance.json`: data/dashboard/wnba_full_game_performance.json, data/warehouse/wnba_full_game_performance.json
- `wnba_full_game_simulation_v2.json`: data/dashboard/wnba_full_game_simulation_v2.json, data/warehouse/wnba_full_game_simulation_v2.json
- `wnba_game_market_model.json`: data/dashboard/wnba_game_market_model.json, data/warehouse/wnba_game_market_model.json
- `wnba_game_predictions.json`: data/dashboard/wnba_game_predictions.json, data/warehouse/wnba_game_predictions.json
- `wnba_game_predictions_ledger.json`: data/dashboard/wnba_game_predictions_ledger.json, data/warehouse/wnba_game_predictions_ledger.json
- `wnba_game_props_q1.json`: data/dashboard/wnba_game_props_q1.json, data/warehouse/wnba_game_props_q1.json
- `wnba_historical_prediction_reconstruction.json`: data/dashboard/wnba_historical_prediction_reconstruction.json, data/warehouse/wnba_historical_prediction_reconstruction.json
- `wnba_historical_summary.json`: data/dashboard/wnba_historical_summary.json, data/warehouse/wnba_historical_summary.json
- `wnba_hyperparameter_optimizer.json`: data/dashboard/wnba_hyperparameter_optimizer.json, data/warehouse/wnba_hyperparameter_optimizer.json
- `wnba_injury_intelligence.json`: data/dashboard/wnba_injury_intelligence.json, data/warehouse/wnba_injury_intelligence.json
- `wnba_live_odds_layer.json`: data/dashboard/wnba_live_odds_layer.json, data/warehouse/wnba_live_odds_layer.json
- `wnba_live_results_engine.json`: data/dashboard/wnba_live_results_engine.json, data/warehouse/wnba_live_results_engine.json
- `wnba_live_slate_status.json`: data/dashboard/wnba_live_slate_status.json, data/warehouse/wnba_live_slate_status.json
- `wnba_market_engine.json`: data/dashboard/wnba_market_engine.json, data/warehouse/wnba_market_engine.json
- `wnba_market_intelligence.json`: data/dashboard/wnba_market_intelligence.json, data/warehouse/wnba_market_intelligence.json
- `wnba_master.json`: data/dashboard/wnba_master.json, data/master/wnba_master.json
- `wnba_master_database_summary.json`: data/dashboard/wnba_master_database_summary.json, data/warehouse/wnba_master_database_summary.json
- `wnba_matchup_intelligence.json`: data/dashboard/wnba_matchup_intelligence.json, data/warehouse/wnba_matchup_intelligence.json
- `wnba_minutes_projection_v2.json`: data/dashboard/wnba_minutes_projection_v2.json, data/warehouse/wnba_minutes_projection_v2.json
- `wnba_mission_control.json`: data/dashboard/wnba_mission_control.json, data/warehouse/wnba_mission_control.json
- `wnba_model_audit.json`: data/dashboard/wnba_model_audit.json, data/warehouse/wnba_model_audit.json
- `wnba_model_calibration.json`: data/dashboard/wnba_model_calibration.json, data/warehouse/wnba_model_calibration.json
- `wnba_model_explainability.json`: data/dashboard/wnba_model_explainability.json, data/warehouse/wnba_model_explainability.json
- `wnba_model_picks_ledger.json`: data/dashboard/wnba_model_picks_ledger.json, data/warehouse/wnba_model_picks_ledger.json
- `wnba_model_quality_audit.json`: data/dashboard/wnba_model_quality_audit.json, data/warehouse/wnba_model_quality_audit.json
- `wnba_monte_carlo_engine.json`: data/dashboard/wnba_monte_carlo_engine.json, data/warehouse/wnba_monte_carlo_engine.json
- `wnba_monte_carlo_scenarios.json`: data/dashboard/wnba_monte_carlo_scenarios.json, data/warehouse/wnba_monte_carlo_scenarios.json
- `wnba_odds_health.json`: data/dashboard/wnba_odds_health.json, data/warehouse/wnba_odds_health.json
- `wnba_odds_history_dashboard.json`: data/dashboard/wnba_odds_history_dashboard.json, data/warehouse/wnba_odds_history_dashboard.json
- `wnba_odds_history_outcomes.json`: data/dashboard/wnba_odds_history_outcomes.json, data/warehouse/wnba_odds_history_outcomes.json
- `wnba_odds_history_results.json`: data/dashboard/wnba_odds_history_results.json, data/warehouse/wnba_odds_history_results.json
- `wnba_odds_history_trends.json`: data/dashboard/wnba_odds_history_trends.json, data/warehouse/wnba_odds_history_trends.json
- `wnba_opponent_stat_rankings.json`: data/dashboard/wnba_opponent_stat_rankings.json, data/warehouse/wnba_opponent_stat_rankings.json
- `wnba_opportunity_rankings.json`: data/dashboard/wnba_opportunity_rankings.json, data/warehouse/wnba_opportunity_rankings.json
- `wnba_pace_minutes_opponent_rankings.json`: data/dashboard/wnba_pace_minutes_opponent_rankings.json, data/warehouse/wnba_pace_minutes_opponent_rankings.json
- `wnba_parlay_optimizer_v2.json`: data/dashboard/wnba_parlay_optimizer_v2.json, data/warehouse/wnba_parlay_optimizer_v2.json
- `wnba_phase5_backtest.json`: data/dashboard/wnba_phase5_backtest.json, data/warehouse/wnba_phase5_backtest.json
- `wnba_phase5_learning.json`: data/dashboard/wnba_phase5_learning.json, data/warehouse/wnba_phase5_learning.json
- `wnba_pipeline_readiness.json`: data/dashboard/wnba_pipeline_readiness.json, data/warehouse/wnba_pipeline_readiness.json
- `wnba_play_by_play_layer.json`: data/dashboard/wnba_play_by_play_layer.json, data/warehouse/wnba_play_by_play_layer.json
- `wnba_player_game_logs.json`: data/dashboard/wnba_player_game_logs.json, data/warehouse/wnba_player_game_logs.json
- `wnba_player_intelligence.json`: data/dashboard/wnba_player_intelligence.json, data/warehouse/wnba_player_intelligence.json
- `wnba_player_prop_grading_bridge.json`: data/dashboard/wnba_player_prop_grading_bridge.json, data/warehouse/wnba_player_prop_grading_bridge.json
- `wnba_player_prop_intelligence.json`: data/dashboard/wnba_player_prop_intelligence.json, data/warehouse/wnba_player_prop_intelligence.json
- `wnba_points_projection_v2.json`: data/dashboard/wnba_points_projection_v2.json, data/warehouse/wnba_points_projection_v2.json
- `wnba_portfolio_dashboard.json`: data/dashboard/wnba_portfolio_dashboard.json, data/warehouse/wnba_portfolio_dashboard.json
- `wnba_portfolio_optimizer_v2.json`: data/dashboard/wnba_portfolio_optimizer_v2.json, data/warehouse/wnba_portfolio_optimizer_v2.json
- `wnba_position_opponent_rankings.json`: data/dashboard/wnba_position_opponent_rankings.json, data/warehouse/wnba_position_opponent_rankings.json
- `wnba_production_readiness.json`: data/dashboard/wnba_production_readiness.json, data/warehouse/wnba_production_readiness.json
- `wnba_projection_ai.json`: data/dashboard/wnba_projection_ai.json, data/warehouse/wnba_projection_ai.json
- `wnba_projection_performance.json`: data/dashboard/wnba_projection_performance.json, data/warehouse/wnba_projection_performance.json
- `wnba_prop_bet_cards.json`: data/dashboard/wnba_prop_bet_cards.json, data/warehouse/wnba_prop_bet_cards.json
- `wnba_prop_card_performance.json`: data/dashboard/wnba_prop_card_performance.json, data/warehouse/wnba_prop_card_performance.json
- `wnba_q1_team_history.json`: data/dashboard/wnba_q1_team_history.json, data/warehouse/wnba_q1_team_history.json
- `wnba_reasoning_layer.json`: data/dashboard/wnba_reasoning_layer.json, data/warehouse/wnba_reasoning_layer.json
- `wnba_rebounds_assists_projection_v2.json`: data/dashboard/wnba_rebounds_assists_projection_v2.json, data/warehouse/wnba_rebounds_assists_projection_v2.json
- `wnba_results_grading.json`: data/dashboard/wnba_results_grading.json, data/warehouse/wnba_results_grading.json
- `wnba_risk_allocation.json`: data/dashboard/wnba_risk_allocation.json, data/warehouse/wnba_risk_allocation.json
- `wnba_self_learning.json`: data/dashboard/wnba_self_learning.json, data/warehouse/wnba_self_learning.json
- `wnba_source_health.json`: data/dashboard/wnba_source_health.json, data/warehouse/wnba_source_health.json
- `wnba_source_shopping.json`: data/dashboard/wnba_source_shopping.json, data/warehouse/wnba_source_shopping.json
- `wnba_sportsbook_consensus.json`: data/dashboard/wnba_sportsbook_consensus.json, data/warehouse/wnba_sportsbook_consensus.json
- `wnba_standings.json`: data/dashboard/wnba_standings.json, data/warehouse/wnba_standings.json
- `wnba_stats_quality.json`: data/dashboard/wnba_stats_quality.json, data/warehouse/wnba_stats_quality.json
- `wnba_unified_player_simulation_v2.json`: data/dashboard/wnba_unified_player_simulation_v2.json, data/warehouse/wnba_unified_player_simulation_v2.json
- `wnba_v5_model_intelligence.json`: data/dashboard/wnba_v5_model_intelligence.json, data/warehouse/wnba_v5_model_intelligence.json
- `wnba_v5_player_profiles.json`: data/dashboard/wnba_v5_player_profiles.json, data/warehouse/wnba_v5_player_profiles.json
- `wnba_v5_sportsbook_intelligence.json`: data/dashboard/wnba_v5_sportsbook_intelligence.json, data/warehouse/wnba_v5_sportsbook_intelligence.json
- `wnba_vote_layer_v2.json`: data/dashboard/wnba_vote_layer_v2.json, data/warehouse/wnba_vote_layer_v2.json
