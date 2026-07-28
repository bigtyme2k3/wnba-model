"""Archive and grade Sprint 23 shadow player-prop opportunities.

This module never places bets or changes production recommendations. It maintains a
snapshot ledger, grades completed markets against verified player game logs, measures
$1-unit ROI and closing-line movement, and produces promotion evidence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CURRENT = Path("data/processed/sprint23/props_market_opportunities_shadow.csv")
OUT = Path("data/processed/sprint23/validation")
LEDGER = OUT / "shadow_opportunity_ledger.csv"
GRADED = OUT / "shadow_opportunities_graded.csv"
SUMMARY = OUT / "shadow_validation_summary.csv"
CATALOG = OUT / "shadow_validation_catalog.json"
LOG_CANDIDATES = [
    Path("data/warehouse/sprint22/player/player_game_logs.csv"),
    Path("data/raw/player_game_logs_2026.csv"),
]
KEY = ["game_date", "event_id", "player_id", "stat", "side", "sportsbook_key", "line", "odds"]


def american_profit(odds: float) -> float:
    return odds / 100.0 if odds > 0 else 100.0 / abs(odds)


def implied_probability(odds: float) -> float:
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)


def find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lookup = {str(c).lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    return None


def load_actuals() -> pd.DataFrame:
    path = next((p for p in LOG_CANDIDATES if p.exists()), None)
    if path is None:
        return pd.DataFrame(columns=["game_date", "player_id", "pts", "reb", "ast", "threes", "pra"])
    raw = pd.read_csv(path, low_memory=False)
    date_col = find_col(raw, ["game_date", "date"])
    player_col = find_col(raw, ["player_id", "athlete_id"])
    if not date_col or not player_col:
        return pd.DataFrame(columns=["game_date", "player_id", "pts", "reb", "ast", "threes", "pra"])
    out = pd.DataFrame({
        "game_date": pd.to_datetime(raw[date_col], errors="coerce").dt.date.astype("string"),
        "player_id": raw[player_col].astype("string"),
    })
    aliases = {
        "pts": ["points", "pts"],
        "reb": ["rebounds", "reb", "total_rebounds"],
        "ast": ["assists", "ast"],
        "threes": ["three_pointers_made", "three_point_field_goals_made", "three_pointers", "threes", "3pm"],
    }
    for stat, names in aliases.items():
        col = find_col(raw, names)
        out[stat] = pd.to_numeric(raw[col], errors="coerce") if col else np.nan
    out["pra"] = out[["pts", "reb", "ast"]].sum(axis=1, min_count=3)
    out = out.dropna(subset=["game_date", "player_id"]).drop_duplicates(["game_date", "player_id"], keep="last")
    return out


def archive_current(now: str) -> pd.DataFrame:
    current = pd.read_csv(CURRENT, low_memory=False) if CURRENT.exists() else pd.DataFrame()
    previous = pd.read_csv(LEDGER, low_memory=False) if LEDGER.exists() else pd.DataFrame()
    if current.empty:
        return previous
    current = current.copy()
    current["snapshot_at_utc"] = now
    current["game_date"] = pd.to_datetime(current["game_date"], errors="coerce").dt.date.astype("string")
    for col in KEY:
        if col not in current.columns:
            current[col] = ""
    combined = pd.concat([previous, current], ignore_index=True, sort=False)
    dedupe = KEY + ["snapshot_at_utc"]
    combined = combined.drop_duplicates(dedupe, keep="last")
    combined.to_csv(LEDGER, index=False)
    return combined


def grade(ledger: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return ledger.copy()
    data = ledger.copy()
    data["game_date"] = pd.to_datetime(data["game_date"], errors="coerce").dt.date.astype("string")
    data["player_id"] = data["player_id"].astype("string")
    data["snapshot_at_utc"] = pd.to_datetime(data["snapshot_at_utc"], errors="coerce", utc=True)
    market_key = ["game_date", "event_id", "player_id", "stat", "side", "sportsbook_key"]
    data = data.sort_values("snapshot_at_utc")
    data["opening_line"] = data.groupby(market_key)["line"].transform("first")
    data["closing_line"] = data.groupby(market_key)["line"].transform("last")
    data["opening_odds"] = data.groupby(market_key)["odds"].transform("first")
    data["closing_odds"] = data.groupby(market_key)["odds"].transform("last")
    data["is_entry_snapshot"] = data.groupby(market_key).cumcount().eq(0)
    entries = data[data["is_entry_snapshot"]].copy()
    entries = entries.merge(actuals, on=["game_date", "player_id"], how="left", suffixes=("", "_actual"))
    entries["actual_value"] = np.nan
    for stat in ["pts", "reb", "ast", "threes", "pra"]:
        mask = entries["stat"].astype(str).str.lower().eq(stat)
        entries.loc[mask, "actual_value"] = pd.to_numeric(entries.loc[mask, stat], errors="coerce")
    entries["line"] = pd.to_numeric(entries["line"], errors="coerce")
    entries["odds"] = pd.to_numeric(entries["odds"], errors="coerce")
    entries["closing_line"] = pd.to_numeric(entries["closing_line"], errors="coerce")
    entries["closing_odds"] = pd.to_numeric(entries["closing_odds"], errors="coerce")
    entries["result"] = "PENDING"
    graded = entries["actual_value"].notna() & entries["line"].notna()
    push = graded & entries["actual_value"].eq(entries["line"])
    over_win = graded & entries["side"].eq("OVER") & entries["actual_value"].gt(entries["line"])
    under_win = graded & entries["side"].eq("UNDER") & entries["actual_value"].lt(entries["line"])
    entries.loc[graded, "result"] = "LOSS"
    entries.loc[over_win | under_win, "result"] = "WIN"
    entries.loc[push, "result"] = "PUSH"
    entries["profit_per_dollar"] = np.nan
    entries.loc[entries["result"].eq("LOSS"), "profit_per_dollar"] = -1.0
    entries.loc[entries["result"].eq("PUSH"), "profit_per_dollar"] = 0.0
    win_mask = entries["result"].eq("WIN") & entries["odds"].notna()
    entries.loc[win_mask, "profit_per_dollar"] = entries.loc[win_mask, "odds"].map(american_profit)
    entries["line_clv"] = np.where(
        entries["side"].eq("OVER"), entries["closing_line"] - entries["line"], entries["line"] - entries["closing_line"]
    )
    entry_ip = entries["odds"].map(lambda x: implied_probability(x) if pd.notna(x) else np.nan)
    close_ip = entries["closing_odds"].map(lambda x: implied_probability(x) if pd.notna(x) else np.nan)
    entries["price_clv"] = close_ip - entry_ip
    entries.to_csv(GRADED, index=False)
    return entries


def summarize(graded: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    completed = graded[graded["result"].isin(["WIN", "LOSS", "PUSH"])].copy() if not graded.empty else pd.DataFrame()
    rows = []
    if not completed.empty:
        for dims, group in completed.groupby(["stat", "sportsbook_key", "side"], dropna=False):
            decisions = group[group["result"].isin(["WIN", "LOSS"])]
            rows.append({
                "stat": dims[0], "sportsbook_key": dims[1], "side": dims[2],
                "graded_rows": int(len(group)), "decisions": int(len(decisions)),
                "wins": int(group["result"].eq("WIN").sum()), "losses": int(group["result"].eq("LOSS").sum()),
                "pushes": int(group["result"].eq("PUSH").sum()),
                "hit_rate": float(group["result"].eq("WIN").sum() / len(decisions)) if len(decisions) else np.nan,
                "roi_per_dollar": float(group["profit_per_dollar"].mean()),
                "avg_model_ev": float(pd.to_numeric(group["expected_value_per_dollar"], errors="coerce").mean()),
                "avg_line_clv": float(pd.to_numeric(group["line_clv"], errors="coerce").mean()),
                "avg_price_clv": float(pd.to_numeric(group["price_clv"], errors="coerce").mean()),
            })
    summary = pd.DataFrame(rows)
    summary.to_csv(SUMMARY, index=False)
    decisions = completed[completed["result"].isin(["WIN", "LOSS"])] if not completed.empty else completed
    graded_count = int(len(completed))
    roi = float(completed["profit_per_dollar"].mean()) if graded_count else None
    hit_rate = float(completed["result"].eq("WIN").sum() / len(decisions)) if len(decisions) else None
    avg_line_clv = float(pd.to_numeric(completed["line_clv"], errors="coerce").mean()) if graded_count else None
    minimum = 200
    promotion_ready = bool(graded_count >= minimum and roi is not None and roi > 0 and avg_line_clv is not None and avg_line_clv >= 0)
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "sprint23_phase4_shadow_validation_v1",
        "status": "PASS",
        "deployment_status": "SHADOW_ONLY",
        "ledger_rows": int(len(graded)),
        "graded_rows": graded_count,
        "pending_rows": int(graded["result"].eq("PENDING").sum()) if not graded.empty else 0,
        "wins": int(completed["result"].eq("WIN").sum()) if graded_count else 0,
        "losses": int(completed["result"].eq("LOSS").sum()) if graded_count else 0,
        "pushes": int(completed["result"].eq("PUSH").sum()) if graded_count else 0,
        "hit_rate": hit_rate,
        "roi_per_dollar": roi,
        "avg_line_clv": avg_line_clv,
        "minimum_graded_for_promotion_review": minimum,
        "promotion_review_status": "ELIGIBLE_FOR_REVIEW" if promotion_ready else "INSUFFICIENT_EVIDENCE",
        "production_recommendations_changed": False,
        "unit_definition": "$1 hypothetical flat stake per archived opening snapshot.",
    }
    CATALOG.write_text(json.dumps(catalog, indent=2, allow_nan=False))
    return summary, catalog


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    ledger = archive_current(now)
    actuals = load_actuals()
    graded = grade(ledger, actuals)
    _, catalog = summarize(graded)
    print("Sprint 23 Phase 4:", catalog)
    return catalog


if __name__ == "__main__":
    build()
