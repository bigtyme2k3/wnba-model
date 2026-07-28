"""Build shadow player-prop opportunities from verified features, shadow models, and book lines."""
from __future__ import annotations

import json
import math
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

FEATURES = Path("data/features/sprint23/player/player_latest_features.csv")
LINES = Path("data/raw/line_shopping_today.csv")
MODEL = Path("models/sprint23/props_models_shadow.pkl")
EVAL = Path("models/sprint23/props_shadow_evaluation.json")
OUT = Path("data/processed/sprint23")
BOOKS = {"draftkings", "fanduel"}
STAT_MAP = {"PTS": "pts", "REB": "reb", "AST": "ast", "3PM": "threes", "PRA": "pra"}
OUTPUT_COLUMNS = [
    "generated_at_utc", "game_date", "event_id", "game", "player", "player_id", "stat", "side",
    "sportsbook", "sportsbook_key", "line", "odds", "projection", "projection_edge", "model_probability",
    "implied_probability", "probability_edge", "expected_value_per_dollar", "model_mae", "feature_ready",
    "deployment_status", "source"
]


def normalize_name(value: object) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(value).lower())
    return " ".join(text.split())


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def implied_probability(odds: float) -> float:
    return 100.0 / (odds + 100.0) if odds > 0 else (-odds) / ((-odds) + 100.0)


def profit_per_dollar(odds: float) -> float:
    return odds / 100.0 if odds > 0 else 100.0 / (-odds)


def empty_output() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    features = pd.read_csv(FEATURES, low_memory=False)
    lines = pd.read_csv(LINES, low_memory=False) if LINES.exists() else pd.DataFrame()
    with MODEL.open("rb") as fh:
        bundle = pickle.load(fh)
    evaluation = json.loads(EVAL.read_text())
    models = bundle["models"]
    generated_at = datetime.now(timezone.utc).isoformat()

    features["player_key"] = features["player"].map(normalize_name)
    features = features.sort_values(["player_id", "game_date"]).drop_duplicates("player_key", keep="last")

    if lines.empty:
        opportunities = empty_output()
        unmatched = pd.DataFrame(columns=["player", "player_key", "stat", "side", "book_key", "line", "odds"])
    else:
        market = lines.copy()
        market = market[(market.get("market_type", "") == "PROP") & market["book_key"].astype(str).str.lower().isin(BOOKS)].copy()
        market["player_key"] = market["player"].map(normalize_name)
        market["target"] = market["stat"].astype(str).str.upper().map(STAT_MAP)
        market["side"] = market["side"].astype(str).str.upper()
        market["line"] = pd.to_numeric(market["line"], errors="coerce")
        market["odds"] = pd.to_numeric(market["odds"], errors="coerce")
        market = market[market["target"].notna() & market["side"].isin(["OVER", "UNDER"]) & market["line"].notna() & market["odds"].notna()].copy()
        joined = market.merge(features, on="player_key", how="left", suffixes=("", "_feature"), indicator=True)
        unmatched = joined[joined["_merge"] != "both"][["player", "player_key", "stat", "side", "book_key", "line", "odds"]].copy()
        joined = joined[joined["_merge"] == "both"].copy()
        rows = []
        for _, row in joined.iterrows():
            target = row["target"]
            if target not in models:
                continue
            model_info = models[target]
            feature_names = model_info["features"]
            x = pd.DataFrame([{name: pd.to_numeric(pd.Series([row.get(name)]), errors="coerce").fillna(0).iloc[0] for name in feature_names}])
            projection = float(model_info["model"].predict(x[feature_names])[0])
            line = float(row["line"]); odds = float(row["odds"]); side = row["side"]
            edge = projection - line
            mae = float(evaluation.get("metrics", {}).get(target, {}).get("mae") or 1.0)
            sigma = max(mae * 1.253314, 0.25)
            over_prob = 1.0 - normal_cdf((line - projection) / sigma)
            model_prob = over_prob if side == "OVER" else 1.0 - over_prob
            implied = implied_probability(odds)
            ev = model_prob * profit_per_dollar(odds) - (1.0 - model_prob)
            rows.append({
                "generated_at_utc": generated_at, "game_date": row.get("game_date", ""), "event_id": row.get("event_id", ""),
                "game": row.get("game", ""), "player": row.get("player", ""), "player_id": row.get("player_id", ""),
                "stat": target, "side": side, "sportsbook": row.get("book_title", ""), "sportsbook_key": str(row.get("book_key", "")).lower(),
                "line": round(line, 2), "odds": int(odds), "projection": round(projection, 2),
                "projection_edge": round(edge if side == "OVER" else -edge, 2), "model_probability": round(model_prob, 4),
                "implied_probability": round(implied, 4), "probability_edge": round(model_prob - implied, 4),
                "expected_value_per_dollar": round(ev, 4), "model_mae": round(mae, 3),
                "feature_ready": bool(row.get("feature_ready", False)), "deployment_status": "SHADOW_ONLY",
                "source": "sprint23_phase3_shadow"
            })
        opportunities = pd.DataFrame(rows, columns=OUTPUT_COLUMNS) if rows else empty_output()
        if not opportunities.empty:
            opportunities = opportunities.sort_values(["expected_value_per_dollar", "probability_edge"], ascending=False).reset_index(drop=True)

    opportunities.to_csv(OUT / "props_market_opportunities_shadow.csv", index=False)
    unmatched.to_csv(OUT / "props_market_unmatched_shadow.csv", index=False)
    positive = int((pd.to_numeric(opportunities.get("expected_value_per_dollar", pd.Series(dtype=float)), errors="coerce") > 0).sum())
    catalog = {
        "generated_at_utc": generated_at,
        "version": "sprint23_phase3_shadow_v1",
        "status": "PASS" if not opportunities.empty else "EMPTY",
        "deployment_status": "SHADOW_ONLY",
        "books_allowed": sorted(BOOKS),
        "market_rows_scored": int(len(opportunities)),
        "positive_ev_rows": positive,
        "matched_players": int(opportunities["player_id"].nunique()) if not opportunities.empty else 0,
        "unmatched_market_rows": int(len(unmatched)),
        "production_recommendations_changed": False,
        "ev_definition": "Expected profit per $1 staked using shadow model probability and listed American odds.",
    }
    (OUT / "props_market_opportunity_catalog.json").write_text(json.dumps(catalog, indent=2))
    print("Sprint 23 Phase 3:", catalog)
    return catalog


if __name__ == "__main__":
    build()
