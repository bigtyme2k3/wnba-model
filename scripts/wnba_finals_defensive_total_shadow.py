#!/usr/bin/env python3
"""Research-only defensive total challenger. Never modifies production predictions."""
import json
from datetime import datetime, timezone
from pathlib import Path

PRED = Path("data/dashboard/wnba_s19_m02_predictions.json")
HISTORY = Path("data/dashboard/wnba_game_performance.json")
OUTPUT = Path("data/dashboard/wnba_finals_defensive_total_shadow.json")

def build(predictions, performance):
    target = predictions["target_date"]
    results = []
    for game in predictions.get("games", []):
        baseline = game.get("projection", {}).get("total")
        if not isinstance(baseline, (int, float)):
            continue
        teams = {game.get("away_team"), game.get("home_team")}
        previous = [
            r for r in performance.get("recent_games", [])
            if r.get("status") == "GRADED"
            and str(r.get("target_date", "")) < target
            and teams == {r.get("away_team"), r.get("home_team")}
            and isinstance(r.get("actual_total"), (int, float))
            and isinstance(r.get("projected_total"), (int, float))
        ]
        previous.sort(key=lambda r: (r["target_date"], str(r.get("prediction_id", ""))))
        residuals = [r["actual_total"] - r["projected_total"] for r in previous[-3:]]
        # Explicit exploratory parameters, not calibrated or production-approved.
        raw_adjustment = (sum(residuals) / len(residuals) * 0.25) if residuals else 0
        adjustment = max(-6.0, min(6.0, raw_adjustment))
        challenger = round(baseline + adjustment, 2)
        market = game.get("market", {}).get("total")
        results.append({
            "game": game["game"], "target_date": target,
            "baseline_total": baseline, "shadow_total": challenger,
            "adjustment": round(adjustment, 2),
            "prior_head_to_head_games": len(residuals),
            "prior_prediction_ids": [r.get("prediction_id") for r in previous[-3:]],
            "market_total_reference_only": market,
            "shadow_vs_market": round(challenger - market, 2) if isinstance(market, (int, float)) else None,
            "recommendation": "PASS",
        })
    return {
        "status": "SHADOW_RESEARCH_ONLY", "target_date": target,
        "source_prediction_generated_at_utc": predictions.get("generated_at_utc"),
        "source_performance_generated_at_utc": performance.get("generated_at_utc"),
        "method": "prior_same_matchup_total_residual_25pct_shrinkage_capped_6_points",
        "parameters_calibrated": False, "production_mutation": False,
        "bet_recommendation": "PASS",
        "limitations": ["Exploratory adjustment; no backtest edge established",
                        "Small head-to-head sample; no possession data",
                        "Market total is not a verified executable sportsbook price"],
        "games": results,
    }

def main():
    out = build(json.loads(PRED.read_text()), json.loads(HISTORY.read_text()))
    out["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    OUTPUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
