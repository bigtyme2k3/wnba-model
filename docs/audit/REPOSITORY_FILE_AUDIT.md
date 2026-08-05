# WNBA Repository File Audit

Generated: `2026-08-05T21:07:03.350909+00:00`

## Summary

- **ARCHIVE:** 119
- **DOC:** 39
- **GENERATED:** 630
- **KEEP:** 260
- **REVIEW:** 412
- **REVIEW_DUPLICATE:** 17

## Cleanup interpretation

- **KEEP:** active production dependency or canonical infrastructure.
- **GENERATED:** output data. Retention should be governed by a clear current/history policy.
- **ARCHIVE:** intentionally non-production.
- **REVIEW / REVIEW_DUPLICATE:** strongest cleanup candidates. Do not delete until ownership and history needs are confirmed.

## Highest-priority review candidates

- `advanced_model_upgrades.py` — Unreferenced Python script; confirm manual use before archive/delete
- `archive_best_bets.py` — Unreferenced Python script; confirm manual use before archive/delete
- `autonomous_intelligence.py` — Unreferenced Python script; confirm manual use before archive/delete
- `bootstrap.yml` — Filename also exists in archived workflow area
- `build_sprint22_phase2_player_warehouse_numeric.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint22_player_coverage_manifest.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint23_phase1_player_features.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint23_phase2_props_dataset.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint23_phase3_market_opportunities.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint23_phase4_shadow_validation.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint23_phase5_explainable_shadow.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_sprint24_phase1_shadow_governance.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_wnba_alt_exception_packet.py` — Unreferenced Python script; confirm manual use before archive/delete
- `build_wnba_v5_model_intelligence.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_wnba_v5_player_profiles.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `build_wnba_v5_sportsbook_intelligence.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `collect_sprint22_historical_player_native_r.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `collect_sprint22_historical_player_only.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `collect_sprint24_phase2_live_lines.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `config/market_registry.json` — No active workflow/import reference found
- `config/source_registry.json` — No active workflow/import reference found
- `config/v4_modules.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `config/wnba_learned_weights.json` — No active workflow/import reference found
- `daily_action_report_v2.py` — Versioned/legacy naming suggests overlap or superseded implementation
- `daily_pipeline.yml` — No active workflow/import reference found
- `daily_predictions.py` — Unreferenced Python script; confirm manual use before archive/delete
- `dashboard_health.py` — Unreferenced Python script; confirm manual use before archive/delete
- `data/advanced/advanced_context_2026-07-06.json` — No active workflow/import reference found
- `data/advanced/advanced_context_2026-07-07.json` — No active workflow/import reference found
- `data/advanced/advanced_context_2026-07-08.json` — No active workflow/import reference found
- `data/advanced/advanced_context_2026-07-09.json` — No active workflow/import reference found
- `data/audit/best_feature_set.json` — No active workflow/import reference found
- `data/audit/ev_trace_report.json` — No active workflow/import reference found
- `data/audit/feature_correlations.json` — No active workflow/import reference found
- `data/audit/feature_importance.json` — No active workflow/import reference found
- `data/audit/feature_rankings.json` — No active workflow/import reference found
- `data/audit/feature_set_comparison.json` — No active workflow/import reference found
- `data/audit/market_feature_recommendations.json` — No active workflow/import reference found
- `data/audit/phase_a_calculation_audit.json` — No active workflow/import reference found
- `data/audit/phase_b_data_flow_audit.json` — No active workflow/import reference found
- `data/audit/phase_c_calibration_report.json` — No active workflow/import reference found
- `data/audit/phase_d_calibration_validation.json` — No active workflow/import reference found
- `data/audit/phase_d_validation_curves.json` — No active workflow/import reference found
- `data/audit/phase_e_ranking_market_validation.json` — No active workflow/import reference found
- `data/audit/phase_e_segment_validation.json` — No active workflow/import reference found
- `data/audit/probability_calibration_curve.json` — No active workflow/import reference found
- `data/audit/probability_source_trace.json` — No active workflow/import reference found
- `data/audit/recommended_feature_set.json` — No active workflow/import reference found
- `data/audit/rolling_validation_results.json` — No active workflow/import reference found
- `data/audit/simulation_distribution.json` — No active workflow/import reference found
- `data/audit/sprint21_phase3_best_model.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/audit/sprint21_phase3_feature_manifest.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/audit/sprint21_phase3_market_models.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/audit/sprint21_phase3_model_comparison.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/features/sprint23/player/player_feature_catalog.json` — No active workflow/import reference found
- `data/features/sprint23/player/player_game_features.csv` — No active workflow/import reference found
- `data/features/sprint23/player/player_latest_features.csv` — No active workflow/import reference found
- `data/health/wnba_foundation_market_refresh.json` — No active workflow/import reference found
- `data/health/wnba_foundation_optional_providers.json` — No active workflow/import reference found
- `data/history/best_bets_ledger.csv` — No active workflow/import reference found
- `data/history/best_bets_performance.csv` — No active workflow/import reference found
- `data/history/best_bets_summary.json` — No active workflow/import reference found
- `data/history/line_shopping_history.jsonl` — No active workflow/import reference found
- `data/history/market_movement_history.jsonl` — No active workflow/import reference found
- `data/history/opportunity_finder_history.jsonl` — No active workflow/import reference found
- `data/history/wnba_alt_market_snapshots.jsonl` — No active workflow/import reference found
- `data/history/wnba_alt_market_watch_state.json` — No active workflow/import reference found
- `data/history/wnba_betting_ledger.jsonl` — No active workflow/import reference found
- `data/history/wnba_edge_database.jsonl` — No active workflow/import reference found
- `data/history/wnba_game_predictions.jsonl` — No active workflow/import reference found
- `data/history/wnba_graded_bets.csv` — No active workflow/import reference found
- `data/history/wnba_line_snapshots.jsonl` — No active workflow/import reference found
- `data/history/wnba_live_results_state.json` — No active workflow/import reference found
- `data/history/wnba_market_observations.jsonl` — No active workflow/import reference found
- `data/history/wnba_master_database.jsonl` — No active workflow/import reference found
- `data/history/wnba_model_history.jsonl` — No active workflow/import reference found
- `data/history/wnba_model_picks_ledger.jsonl` — No active workflow/import reference found
- `data/history/wnba_opportunity_ranking_history.jsonl` — No active workflow/import reference found
- `data/history/wnba_projection_history.jsonl` — No active workflow/import reference found
- `data/history/wnba_prop_card_ledger.jsonl` — No active workflow/import reference found
- `data/intelligence/autonomous_intelligence_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/autonomous_intelligence_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/autonomous_intelligence_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/autonomous_intelligence_2026-07-09.json` — No active workflow/import reference found
- `data/intelligence/daily_action_report_v2_2026-07-06.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/daily_action_report_v2_2026-07-07.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/daily_action_report_v2_2026-07-08.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/daily_action_report_v2_2026-07-09.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/daily_briefing_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/daily_briefing_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/daily_briefing_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/daily_briefing_2026-07-09.json` — No active workflow/import reference found
- `data/intelligence/dashboard_health_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/dashboard_health_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/dashboard_health_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/dashboard_health_2026-07-09.json` — No active workflow/import reference found
- `data/intelligence/decision_center_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/decision_center_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/decision_center_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/decision_center_2026-07-09.json` — No active workflow/import reference found
- `data/intelligence/deepseek_portfolio_optimizer_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/game_command_center_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/game_command_center_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/game_command_center_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/game_command_center_2026-07-09.json` — No active workflow/import reference found
- `data/intelligence/market_heatmap_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/market_heatmap_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/market_timing_intelligence_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/market_timing_intelligence_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/minutes_usage_intelligence_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/minutes_usage_intelligence_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/projection_accuracy_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/projection_accuracy_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/projection_accuracy_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/projection_intelligence_v2_2026-07-06.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/projection_intelligence_v2_2026-07-07.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/projection_intelligence_v2_2026-07-08.json` — Versioned/legacy naming suggests overlap or superseded implementation
- `data/intelligence/results_review_center_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/unified_prediction_score_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/unified_prediction_score_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/unified_prediction_score_2026-07-08.json` — No active workflow/import reference found
- `data/intelligence/unified_prediction_score_2026-07-09.json` — No active workflow/import reference found
- `data/intelligence/wnba_context_engine_2026-07-06.json` — No active workflow/import reference found
- `data/intelligence/wnba_context_engine_2026-07-07.json` — No active workflow/import reference found
- `data/intelligence/wnba_context_engine_2026-07-08.json` — No active workflow/import reference found
- `data/manual/wnba_alt_game_mapping_overrides.csv` — No active workflow/import reference found
- `data/manual/wnba_manual_odds.csv` — No active workflow/import reference found
- `data/processed/master_2022.csv` — No active workflow/import reference found
- `data/processed/master_2023.csv` — No active workflow/import reference found
- `data/processed/master_2024.csv` — No active workflow/import reference found
- `data/processed/master_all.csv` — No active workflow/import reference found
- `data/processed/sprint23/player_props_training.csv` — No active workflow/import reference found
- `data/processed/sprint23/props_integration_catalog.json` — No active workflow/import reference found
- `data/processed/sprint23/props_market_opportunities_shadow.csv` — No active workflow/import reference found
- `data/processed/sprint23/props_market_opportunity_catalog.json` — No active workflow/import reference found
- `data/processed/sprint23/props_market_unmatched_shadow.csv` — No active workflow/import reference found
- `data/processed/sprint23/validation/shadow_opportunities_graded.csv` — No active workflow/import reference found
- `data/processed/sprint23/validation/shadow_opportunity_ledger.csv` — No active workflow/import reference found
- `data/processed/sprint23/validation/shadow_validation_catalog.json` — No active workflow/import reference found
- `data/processed/sprint24/shadow_governance_audit.csv` — No active workflow/import reference found
- `data/processed/sprint24/shadow_governance_catalog.json` — No active workflow/import reference found
- `data/processed/sprint24/shadow_governed_shortlist.csv` — No active workflow/import reference found
- `data/refresh_requests/refresh_2026-08-05_1131.json` — No active workflow/import reference found
- `data/tracking/graded_bets.csv` — No active workflow/import reference found
- `data/tracking/model_tracking.json` — No active workflow/import reference found
- `data/tracking/slip_optimizer.json` — No active workflow/import reference found
- `data/validation/live_performance_analytics.json` — No active workflow/import reference found
- `data/validation/live_prediction_results.json` — No active workflow/import reference found
- `data/validation/live_prediction_tracker.json` — No active workflow/import reference found
- `data/validation/signal_performance.json` — No active workflow/import reference found

## Recommended cleanup order

1. Resolve byte-identical duplicates.
2. Merge active patch/repair logic into canonical builders.
3. Archive unreferenced versioned scripts and old sprint/phase workflows.
4. Define retention for generated current-state versus historical data.
5. Delete only after one full daily refresh, hourly refresh, grading, and deployment test passes without the candidate files.
