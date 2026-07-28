"""Create a disciplined research-only shortlist from Sprint 23 shadow opportunities."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE = Path("data/processed/sprint23/props_market_opportunities_shadow.csv")
VALIDATION = Path("data/processed/sprint23/validation/shadow_validation_catalog.json")
OUT = Path("data/processed/sprint24")
SHORTLIST = OUT / "shadow_governed_shortlist.csv"
AUDIT = OUT / "shadow_governance_audit.csv"
CATALOG = OUT / "shadow_governance_catalog.json"

ALLOWED_BOOKS = {"draftkings", "fanduel"}
MAX_TOTAL = 20
MAX_PER_PLAYER = 2
MAX_PER_GAME = 6
MAX_PER_STAT = 6
MIN_EV = 0.03
MIN_PROB_EDGE = 0.025
MAX_MAE_RATIO = 0.40


def numeric(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(default, index=frame.index, dtype="float64")


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = pd.read_csv(SOURCE, low_memory=False) if SOURCE.exists() else pd.DataFrame()
    validation = json.loads(VALIDATION.read_text()) if VALIDATION.exists() else {}

    if rows.empty:
        pd.DataFrame().to_csv(SHORTLIST, index=False)
        pd.DataFrame().to_csv(AUDIT, index=False)
        catalog = {
            "generated_at_utc": generated_at,
            "version": "sprint24_phase1_shadow_governance_v1",
            "status": "EMPTY",
            "deployment_status": "SHADOW_ONLY",
            "source_rows": 0,
            "eligible_rows": 0,
            "shortlist_rows": 0,
            "production_recommendations_changed": False,
        }
        CATALOG.write_text(json.dumps(catalog, indent=2))
        print("Sprint 24 Phase 1:", catalog)
        return catalog

    data = rows.copy()
    data["sportsbook_key"] = data.get("sportsbook_key", "").astype(str).str.lower()
    data["stat"] = data.get("stat", "").astype(str).str.lower()
    data["side"] = data.get("side", "").astype(str).str.upper()
    data["expected_value_per_dollar"] = numeric(data, "expected_value_per_dollar")
    data["probability_edge"] = numeric(data, "probability_edge")
    data["model_probability"] = numeric(data, "model_probability")
    data["model_mae"] = numeric(data, "model_mae")
    data["projection_edge"] = numeric(data, "projection_edge")
    data["line"] = numeric(data, "line")
    feature_ready = data.get("feature_ready", False)
    if not isinstance(feature_ready, pd.Series):
        feature_ready = pd.Series(bool(feature_ready), index=data.index)
    data["feature_ready"] = feature_ready.astype(str).str.lower().isin(["true", "1", "yes"])

    data["mae_ratio"] = data["model_mae"] / data["line"].abs().replace(0, np.nan)
    data["uncertainty_penalty"] = np.clip(data["mae_ratio"].fillna(1.0), 0.0, 1.0)
    data["governance_score"] = (
        data["expected_value_per_dollar"].fillna(-1.0) * 100.0
        + data["probability_edge"].fillna(-1.0) * 60.0
        + data["projection_edge"].clip(lower=0).fillna(0.0) * 2.0
        - data["uncertainty_penalty"] * 20.0
    )

    data["base_eligible"] = (
        data["sportsbook_key"].isin(ALLOWED_BOOKS)
        & data["feature_ready"]
        & data["expected_value_per_dollar"].ge(MIN_EV)
        & data["probability_edge"].ge(MIN_PROB_EDGE)
        & data["mae_ratio"].le(MAX_MAE_RATIO)
        & data["side"].isin(["OVER", "UNDER"])
    )

    data["decision"] = "REJECT"
    data["decision_reason"] = "failed minimum governance thresholds"
    data.loc[data["base_eligible"], ["decision", "decision_reason"]] = ["WATCH", "passed minimum thresholds; subject to exposure controls"]

    eligible = data[data["base_eligible"]].copy()
    eligible = eligible.sort_values(
        ["governance_score", "expected_value_per_dollar", "probability_edge"], ascending=False
    )

    # Keep the best listed price for the same player/stat/side/line.
    market_key = ["game_date", "player_id", "stat", "side", "line"]
    eligible = eligible.drop_duplicates(market_key, keep="first")

    selected_indices: list[int] = []
    player_counts: dict[str, int] = {}
    game_counts: dict[str, int] = {}
    stat_counts: dict[str, int] = {}
    for idx, row in eligible.iterrows():
        player = str(row.get("player_id", row.get("player", "")))
        game = str(row.get("event_id", row.get("game", "")))
        stat = str(row.get("stat", ""))
        if len(selected_indices) >= MAX_TOTAL:
            data.loc[idx, "decision_reason"] = "portfolio capacity reached"
            continue
        if player_counts.get(player, 0) >= MAX_PER_PLAYER:
            data.loc[idx, "decision_reason"] = "player exposure limit reached"
            continue
        if game_counts.get(game, 0) >= MAX_PER_GAME:
            data.loc[idx, "decision_reason"] = "game exposure limit reached"
            continue
        if stat_counts.get(stat, 0) >= MAX_PER_STAT:
            data.loc[idx, "decision_reason"] = "stat exposure limit reached"
            continue
        selected_indices.append(idx)
        player_counts[player] = player_counts.get(player, 0) + 1
        game_counts[game] = game_counts.get(game, 0) + 1
        stat_counts[stat] = stat_counts.get(stat, 0) + 1
        data.loc[idx, "decision"] = "SHORTLIST"
        data.loc[idx, "decision_reason"] = "passed thresholds and portfolio exposure controls"

    shortlist = data.loc[selected_indices].copy()
    if not shortlist.empty:
        shortlist = shortlist.sort_values("governance_score", ascending=False).reset_index(drop=True)
        shortlist.insert(0, "governance_rank", range(1, len(shortlist) + 1))
        shortlist["deployment_status"] = "SHADOW_ONLY"
        shortlist["research_stake_units"] = 0.0
        shortlist["governance_generated_at_utc"] = generated_at

    data["governance_generated_at_utc"] = generated_at
    shortlist.to_csv(SHORTLIST, index=False)
    data.to_csv(AUDIT, index=False)

    catalog = {
        "generated_at_utc": generated_at,
        "version": "sprint24_phase1_shadow_governance_v1",
        "status": "PASS",
        "deployment_status": "SHADOW_ONLY",
        "source_rows": int(len(data)),
        "eligible_rows": int(data["base_eligible"].sum()),
        "shortlist_rows": int(len(shortlist)),
        "books_allowed": sorted(ALLOWED_BOOKS),
        "thresholds": {
            "minimum_ev_per_dollar": MIN_EV,
            "minimum_probability_edge": MIN_PROB_EDGE,
            "maximum_mae_to_line_ratio": MAX_MAE_RATIO,
            "maximum_total_shortlist": MAX_TOTAL,
            "maximum_per_player": MAX_PER_PLAYER,
            "maximum_per_game": MAX_PER_GAME,
            "maximum_per_stat": MAX_PER_STAT,
        },
        "validation_context": {
            "graded_rows": validation.get("graded_rows", 0),
            "promotion_review_status": validation.get("promotion_review_status", "INSUFFICIENT_EVIDENCE"),
        },
        "staking_enabled": False,
        "production_recommendations_changed": False,
        "policy": "Research shortlist only. No wager recommendation, automatic promotion, or bankroll allocation.",
    }
    CATALOG.write_text(json.dumps(catalog, indent=2))
    print("Sprint 24 Phase 1:", catalog)
    return catalog


if __name__ == "__main__":
    build()
