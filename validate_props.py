"""
validate_props.py
-----------------
Validates the WNBA props pipeline and explains why the Props tab may be empty.

Checks:
  - PrizePicks raw props file exists
  - raw props has rows
  - points props exist
  - player_points CSV exists
  - player_points CSV has rows

Writes:
  data/raw/props_health.json

Usage:
  python validate_props.py --date 2026-07-05 --raw data/raw --non-strict
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import pandas as pd


def read_csv_if_exists(paths: list[str]) -> tuple[pd.DataFrame, str | None, str | None]:
    for path in paths:
        if os.path.exists(path):
            try:
                return pd.read_csv(path), path, None
            except Exception as exc:
                return pd.DataFrame(), path, str(exc)
    return pd.DataFrame(), None, "file_not_found"


def validate(target_date: str, raw_dir: str, strict: bool = False) -> tuple[dict, int]:
    raw_paths = [
        os.path.join(raw_dir, f"props_raw_{target_date}.csv"),
        os.path.join(raw_dir, "props_today.csv"),
    ]
    points_paths = [
        os.path.join(raw_dir, f"player_points_{target_date}.csv"),
        os.path.join(raw_dir, "player_points_today.csv"),
    ]

    props_df, props_path, props_error = read_csv_if_exists(raw_paths)
    points_df, points_path, points_error = read_csv_if_exists(points_paths)

    health = {
        "status": "unknown",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "props_file": props_path,
        "player_points_file": points_path,
        "raw_props_rows": int(len(props_df)) if props_df is not None else 0,
        "points_props_rows": 0,
        "unique_players": 0,
        "player_points_rows": int(len(points_df)) if points_df is not None else 0,
        "errors": [],
        "warnings": [],
        "next_action": "",
    }

    if props_error:
        health["errors"].append(f"Raw props file issue: {props_error}")
    if props_df.empty:
        health["warnings"].append("PrizePicks raw props file is missing or empty.")
    else:
        if "player" in props_df.columns:
            health["unique_players"] = int(props_df["player"].nunique())
        if "stat" in props_df.columns:
            points = props_df[props_df["stat"].astype(str).str.lower().eq("pts")]
            health["points_props_rows"] = int(len(points))
        elif "stat_raw" in props_df.columns:
            points = props_df[props_df["stat_raw"].astype(str).str.lower().eq("points")]
            health["points_props_rows"] = int(len(points))
        else:
            health["warnings"].append("Props file has no stat/stat_raw column, so points props cannot be detected.")

    if points_error:
        health["errors"].append(f"Player points file issue: {points_error}")
    if points_df.empty:
        health["warnings"].append("player_points CSV is missing or has header only.")

    if props_df.empty:
        health["status"] = "missing_raw_props"
        health["next_action"] = "Open the Scrape props step logs. PrizePicks may have returned no WNBA props or blocked the public API request."
    elif health["points_props_rows"] == 0:
        health["status"] = "no_points_props"
        health["next_action"] = "PrizePicks returned props, but no Points markets. Check stat types in props_today.csv."
    elif points_df.empty:
        health["status"] = "player_points_empty"
        health["next_action"] = "player_points.py ran but produced no rows. Check player_points.py filtering and column names."
    else:
        health["status"] = "ok"
        health["next_action"] = "Props pipeline is working. Dashboard should display player points."

    exit_code = 0 if health["status"] == "ok" or not strict else 1
    return health, exit_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--non-strict", action="store_true", help="Do not fail the workflow if props are unavailable.")
    args = parser.parse_args()

    os.makedirs(args.raw, exist_ok=True)
    health, exit_code = validate(args.date, args.raw, strict=not args.non_strict)

    out = os.path.join(args.raw, "props_health.json")
    with open(out, "w") as f:
        json.dump(health, f, indent=2)

    print("\n═══ PROPS PIPELINE HEALTH ═══\n")
    print(json.dumps(health, indent=2))
    print(f"\nSaved → {out}")
    if health["status"] == "ok":
        print("✅ Props validation passed.")
    else:
        print(f"⚠️ Props validation status: {health['status']}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
