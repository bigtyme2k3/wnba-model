"""Build a dashboard-safe explainable feed for Sprint 23 shadow prop opportunities."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

OPPS = Path("data/processed/sprint23/props_market_opportunities_shadow.csv")
FEATURES = Path("data/features/sprint23/player/player_latest_features.csv")
VALIDATION = Path("data/processed/sprint23/validation/shadow_validation_catalog.json")
OUT = Path("data/dashboard/sprint23_shadow_intelligence.json")
TOP_N = 30

STAT_FEATURES = {
    "pts": ["points_avg_l5", "points_avg_l10", "points_season_avg"],
    "reb": ["rebounds_avg_l5", "rebounds_avg_l10", "rebounds_season_avg"],
    "ast": ["assists_avg_l5", "assists_avg_l10", "assists_season_avg"],
    "threes": ["threes_avg_l5", "threes_avg_l10", "threes_season_avg"],
    "pra": ["pra_avg_l5", "pra_avg_l10"],
}


def num(row: pd.Series, key: str):
    value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def reason(label: str, value, detail: str, direction: str = "support") -> dict:
    return {"label": label, "value": value, "detail": detail, "direction": direction}


def build() -> dict:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    opps = pd.read_csv(OPPS, low_memory=False) if OPPS.exists() else pd.DataFrame()
    features = pd.read_csv(FEATURES, low_memory=False) if FEATURES.exists() else pd.DataFrame()
    validation = json.loads(VALIDATION.read_text()) if VALIDATION.exists() else {}

    feature_index = {}
    if not features.empty and "player_id" in features.columns:
        features["player_id"] = features["player_id"].astype(str)
        feature_index = {str(r["player_id"]): r for _, r in features.iterrows()}

    cards = []
    if not opps.empty:
        work = opps.copy()
        work["expected_value_per_dollar"] = pd.to_numeric(work["expected_value_per_dollar"], errors="coerce")
        work["probability_edge"] = pd.to_numeric(work["probability_edge"], errors="coerce")
        work = work[(work["expected_value_per_dollar"] > 0) & work["feature_ready"].astype(str).str.lower().eq("true")]
        work = work.sort_values(["expected_value_per_dollar", "probability_edge"], ascending=False).head(TOP_N)
        for rank, (_, row) in enumerate(work.iterrows(), start=1):
            f = feature_index.get(str(row.get("player_id")), pd.Series(dtype=object))
            stat = str(row.get("stat", "")).lower()
            reasons = [
                reason("Projection edge", round(float(row.get("projection_edge", 0)), 2), f"Shadow projection {row.get('projection')} vs {row.get('side')} {row.get('line')} line."),
                reason("Probability edge", round(float(row.get("probability_edge", 0)) * 100, 1), "Model probability minus sportsbook implied probability, in percentage points."),
                reason("Expected value", round(float(row.get("expected_value_per_dollar", 0)) * 100, 1), "Estimated profit per $1 hypothetical stake, expressed as a percentage."),
            ]
            for key in STAT_FEATURES.get(stat, []):
                value = num(f, key)
                if value is not None:
                    reasons.append(reason(key.replace("_", " ").title(), round(value, 2), "Pregame historical feature; the current game result is excluded."))
            rest = num(f, "days_rest")
            if rest is not None:
                reasons.append(reason("Rest", round(rest, 1), "Days since the player's previous game.", "context"))
            matchup = num(f, f"matchup_{stat}_avg")
            if matchup is not None:
                reasons.append(reason("Matchup history", round(matchup, 2), "Historical average against the listed opponent before this game."))
            availability = str(f.get("availability_status", "UNKNOWN"))
            cards.append({
                "rank": rank,
                "player": row.get("player", ""), "player_id": str(row.get("player_id", "")),
                "game": row.get("game", ""), "game_date": row.get("game_date", ""),
                "stat": stat, "side": row.get("side", ""), "line": float(row.get("line", 0)),
                "odds": int(row.get("odds", 0)), "sportsbook": row.get("sportsbook", ""),
                "sportsbook_key": row.get("sportsbook_key", ""), "projection": float(row.get("projection", 0)),
                "model_probability": float(row.get("model_probability", 0)),
                "implied_probability": float(row.get("implied_probability", 0)),
                "probability_edge": float(row.get("probability_edge", 0)),
                "expected_value_per_dollar": float(row.get("expected_value_per_dollar", 0)),
                "availability_status": availability, "deployment_status": "SHADOW_ONLY",
                "reasons": reasons,
            })

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "sprint23_phase5_explainable_shadow_v1",
        "status": "PASS",
        "deployment_status": "SHADOW_ONLY",
        "production_recommendations_changed": False,
        "disclaimer": "Research-only shadow signals. Not production recommendations and not automated bets.",
        "cards": cards,
        "card_count": len(cards),
        "validation": {
            "ledger_rows": int(validation.get("ledger_rows", 0) or 0),
            "graded_rows": int(validation.get("graded_rows", 0) or 0),
            "pending_rows": int(validation.get("pending_rows", 0) or 0),
            "hit_rate": validation.get("hit_rate"),
            "roi_per_dollar": validation.get("roi_per_dollar"),
            "avg_line_clv": validation.get("avg_line_clv"),
            "promotion_review_status": validation.get("promotion_review_status", "INSUFFICIENT_EVIDENCE"),
            "minimum_graded_for_promotion_review": int(validation.get("minimum_graded_for_promotion_review", 200) or 200),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, allow_nan=False))
    print("Sprint 23 Phase 5:", {"status": payload["status"], "cards": len(cards), "deployment": payload["deployment_status"]})
    return payload


if __name__ == "__main__":
    build()
