"""Build a single dashboard data bundle from all priority modules."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Any


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        print(f"Warning: could not read {path}: {exc}")
    return default


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def first_existing(*paths: str) -> dict[str, Any]:
    for path in paths:
        value = load_json(path, {})
        if isinstance(value, dict) and value:
            return value
    return {}


def build(target: str):
    bundle = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "source_health": first_existing("data/dashboard/wnba_source_health.json", "data/warehouse/wnba_source_health.json"),
        "odds_health": first_existing("data/dashboard/wnba_odds_health.json", "data/warehouse/wnba_odds_health.json"),
        "sportsbook_consensus": first_existing("data/dashboard/wnba_sportsbook_consensus.json", "data/warehouse/wnba_sportsbook_consensus.json"),
        "live_odds": first_existing("data/dashboard/wnba_live_odds_layer.json", "data/warehouse/wnba_live_odds_layer.json"),
        "projection_ai": first_existing("data/dashboard/wnba_projection_ai.json", "data/warehouse/wnba_projection_ai.json"),
        "ai_coach": first_existing("data/dashboard/wnba_ai_coach.json"),
        "master_database": first_existing("data/dashboard/wnba_master_database_summary.json"),
        "consensus": first_existing("data/dashboard/wnba_consensus_engine.json", "data/warehouse/wnba_consensus_engine.json"),
        "matchups": first_existing("data/dashboard/wnba_matchup_intelligence.json", "data/warehouse/wnba_matchup_intelligence.json"),
        "players": first_existing("data/dashboard/wnba_player_intelligence.json", "data/warehouse/wnba_player_intelligence.json"),
        "monte_carlo": first_existing("data/dashboard/wnba_monte_carlo_engine.json", "data/warehouse/wnba_monte_carlo_engine.json"),
        "market_engine": first_existing("data/dashboard/wnba_market_engine.json", "data/warehouse/wnba_market_engine.json"),
        "portfolio_v2": first_existing("data/dashboard/wnba_portfolio_optimizer_v2.json", "data/warehouse/wnba_portfolio_optimizer_v2.json"),
        "decision_final": first_existing("data/dashboard/wnba_decision_engine_final.json", "data/warehouse/wnba_decision_engine_final.json"),
        "history": first_existing("data/dashboard/wnba_historical_summary.json"),
        "learning": first_existing("data/dashboard/wnba_self_learning.json"),
        "phase5": first_existing("data/dashboard/wnba_phase5_learning.json", "data/warehouse/wnba_phase5_learning.json"),
        "grading": first_existing("data/dashboard/wnba_results_grading.json"),
        "clv": first_existing("data/dashboard/wnba_clv_summary.json"),
        "portfolio": first_existing("data/dashboard/deepseek_portfolio_optimizer.json"),
        "market_timing": first_existing("data/dashboard/market_timing_intelligence.json"),
        "projection_accuracy": first_existing("data/dashboard/projection_accuracy.json"),
    }

    decision = bundle["decision_final"]
    consensus = bundle["consensus"]
    portfolio = bundle["portfolio_v2"]
    health = bundle["source_health"]
    monte_carlo = bundle["monte_carlo"]
    market = bundle["market_engine"]
    odds = bundle["live_odds"]
    odds_health = bundle["odds_health"]
    books = bundle["sportsbook_consensus"]
    coach = bundle["ai_coach"]
    projection = bundle["projection_ai"]
    phase5 = bundle["phase5"]

    top = (decision.get("top_decisions") or consensus.get("top_consensus") or [])[:20]
    sim_summary = monte_carlo.get("summary") or {}
    portfolio_summary = portfolio.get("summary") or {}
    decision_summary = decision.get("summary") or {}
    market_summary = market.get("summary") or {}
    health_summary = health.get("summary") or {}
    odds_summary = odds.get("summary") or {}
    odds_health_summary = odds_health.get("summary") or {}
    book_summary = books.get("summary") or {}
    coach_summary = coach.get("summary") or {}
    projection_summary = projection.get("summary") or {}
    phase5_perf = phase5.get("performance") or {}
    phase5_ready = phase5.get("learning_readiness") or {}

    bundle["terminal_summary"] = {
        "top_cards": top[:5],
        "final_bets": decision_summary.get("bets", 0),
        "final_leans": decision_summary.get("leans", 0),
        "decision_rows": decision_summary.get("rows", len(decision.get("top_decisions") or [])),
        "bet_count": (consensus.get("summary") or {}).get("bets", 0),
        "lean_count": (consensus.get("summary") or {}).get("leans", 0),
        "source_ok": health_summary.get("ok_or_optional", 0),
        "source_total": health_summary.get("sources", 0),
        "source_degraded": health_summary.get("degraded_or_missing", 0),
        "history_records": bundle["history"].get("total_records", 0),
        "graded_this_run": phase5.get("newly_graded", bundle["grading"].get("graded_this_run", 0)),
        "graded_total": phase5_perf.get("graded", 0),
        "win_rate": phase5_perf.get("win_rate"),
        "roi": phase5_perf.get("roi"),
        "units_profit": phase5_perf.get("units_profit"),
        "average_clv": phase5_perf.get("average_clv"),
        "calibration_rows": (phase5.get("calibration") or {}).get("graded_binary_rows", 0),
        "calibration_ready": phase5_ready.get("calibration_ready", False),
        "feature_learning_ready": phase5_ready.get("feature_learning_ready", False),
        "clv_updates": bundle["clv"].get("history_clv_updates", 0),
        "mc_rows": sim_summary.get("rows", len(monte_carlo.get("top_simulations") or [])),
        "mc_prob_60_plus": sim_summary.get("prob_60_plus", 0),
        "mc_low_risk": sim_summary.get("low_risk", 0),
        "portfolio_card_size": portfolio_summary.get("card_size", len(portfolio.get("recommended_card") or [])),
        "portfolio_total_stake": portfolio_summary.get("total_stake", 0),
        "market_rows": market_summary.get("markets", market_summary.get("rows", 0)),
        "live_odds_rows": odds_summary.get("rows", 0),
        "team_spread_rows": odds_health_summary.get("spread_rows", 0),
        "team_total_rows": odds_health_summary.get("total_rows", 0),
        "active_prop_rows": odds_health_summary.get("active_prop_rows", 0),
        "sportsbook_markets": book_summary.get("markets", 0),
        "multi_book_markets": book_summary.get("multi_book_markets", 0),
        "books_detected": book_summary.get("books_detected", []),
        "ai_projection_rows": projection_summary.get("rows", 0),
        "coach_notes": coach_summary.get("notes", 0),
    }

    bundle = clean_json(bundle)
    os.makedirs("data/dashboard", exist_ok=True)
    path = "data/dashboard/terminal_ui.json"
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, allow_nan=False)
    os.replace(temporary, path)
    print(f"Terminal UI bundle built: {bundle['terminal_summary']}")
    return bundle["terminal_summary"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
