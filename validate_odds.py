"""
validate_odds.py
----------------
Validates that The Odds API scrape produced usable WNBA market data.

Checks:
  - odds file exists
  - required columns exist
  - source == the-odds-api
  - at least one game row exists
  - at least one spread or total is populated
  - average bookmaker count is greater than zero

Writes:
  data/raw/odds_health.json

Usage:
  python validate_odds.py --date 2026-07-05 --raw data/raw
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import pandas as pd

REQUIRED_COLUMNS = {
    "game_date", "home_team", "away_team", "spread_home", "total",
    "num_books", "source", "scraped_at"
}


def validate(path: str, strict: bool = True) -> tuple[dict, int]:
    health = {
        "status": "missing",
        "path": path,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": 0,
        "spreads": 0,
        "totals": 0,
        "avg_books": 0,
        "source_ok": False,
        "required_columns_ok": False,
        "errors": [],
    }

    if not os.path.exists(path):
        health["errors"].append(f"Odds file not found: {path}")
        return health, 1 if strict else 0

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        health["errors"].append(f"Could not read odds file: {exc}")
        return health, 1 if strict else 0

    health["rows"] = int(len(df))
    missing_cols = sorted(REQUIRED_COLUMNS - set(df.columns))
    health["required_columns_ok"] = not missing_cols
    if missing_cols:
        health["errors"].append(f"Missing required columns: {missing_cols}")

    if df.empty:
        health["status"] = "empty"
        health["errors"].append("Odds file exists but has zero rows.")
        return health, 1 if strict else 0

    if "source" in df.columns:
        health["source_ok"] = bool((df["source"].astype(str) == "the-odds-api").any())
        if not health["source_ok"]:
            health["errors"].append("No rows marked source=the-odds-api.")

    if "spread_home" in df.columns:
        health["spreads"] = int(df["spread_home"].notna().sum())
    if "total" in df.columns:
        health["totals"] = int(df["total"].notna().sum())
    if "num_books" in df.columns:
        health["avg_books"] = round(float(df["num_books"].fillna(0).mean()), 2)

    if health["spreads"] == 0 and health["totals"] == 0:
        health["errors"].append("No spread or total lines populated.")
    if health["avg_books"] <= 0:
        health["errors"].append("Average bookmaker count is zero.")

    health["status"] = "ok" if not health["errors"] else "warning"
    exit_code = 0 if health["status"] == "ok" else (1 if strict else 0)
    return health, exit_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--non-strict", action="store_true", help="Write health file but do not fail the workflow.")
    args = parser.parse_args()

    path = os.path.join(args.raw, f"odds_{args.date}.csv")
    if not os.path.exists(path):
        path = os.path.join(args.raw, "odds_today.csv")

    health, exit_code = validate(path, strict=not args.non_strict)
    os.makedirs(args.raw, exist_ok=True)
    health_path = os.path.join(args.raw, "odds_health.json")
    with open(health_path, "w") as f:
        json.dump(health, f, indent=2)

    print("\n═══ ODDS API HEALTH ═══\n")
    print(json.dumps(health, indent=2))
    print(f"\nSaved → {health_path}")
    if exit_code == 0:
        print("✅ Odds API validation passed.")
    else:
        print("❌ Odds API validation failed.")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
