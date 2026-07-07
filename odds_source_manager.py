"""
odds_source_manager.py
----------------------
Makes The Odds API optional instead of the primary dependency.

Priority:
1. Manual odds file: data/manual/wnba_manual_odds.csv
2. Current odds file if already populated: data/raw/odds_<date>.csv or odds_today.csv
3. Historical/cache odds: data/raw/odds_historical.csv
4. Empty valid odds file so the pipeline can continue

Outputs:
- data/raw/odds_today.csv
- data/raw/odds_<date>.csv
- data/raw/odds_source_status.json

Manual CSV columns supported:
game_date, home_team, away_team, spread_home, spread_home_juice, total,
total_over_juice, ml_home, ml_away, num_books, source
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd

COLUMNS = [
    "game_date", "game_id", "commence_time", "home_team", "away_team",
    "spread_home", "spread_home_juice", "total", "total_over_juice",
    "ml_home", "ml_away", "num_books", "source", "scraped_at"
]


def empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def read_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return empty_df()
    try:
        df = pd.read_csv(path)
        if df.empty:
            return empty_df()
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[COLUMNS]
    except Exception:
        return empty_df()


def normalize_manual(path: str, target: str) -> pd.DataFrame:
    df = read_csv(path)
    if df.empty:
        return df
    if "game_date" in df.columns:
        df = df[df["game_date"].astype(str).isin([target, "today", "TODAY", ""])]
    if df.empty:
        return empty_df()
    df["game_date"] = target
    df["source"] = df["source"].fillna("manual")
    df["scraped_at"] = datetime.now(timezone.utc).isoformat()
    return df[COLUMNS]


def current_odds(out_dir: str, target: str) -> pd.DataFrame:
    for path in [os.path.join(out_dir, f"odds_{target}.csv"), os.path.join(out_dir, "odds_today.csv")]:
        df = read_csv(path)
        if not df.empty:
            return df
    return empty_df()


def cached_odds(out_dir: str, target: str) -> pd.DataFrame:
    hist = read_csv(os.path.join(out_dir, "odds_historical.csv"))
    if hist.empty:
        return hist
    exact = hist[hist["game_date"].astype(str) == target]
    if not exact.empty:
        exact = exact.copy()
        exact["source"] = exact["source"].fillna("cache") + "+cache_exact"
        return exact[COLUMNS]
    # Last known lines are better than blank dashboard, but mark them clearly.
    hist = hist.copy()
    hist["source"] = hist["source"].fillna("cache") + "+last_known"
    hist["game_date"] = target
    return hist.tail(12)[COLUMNS]


def save(df: pd.DataFrame, target: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    if df.empty:
        df = empty_df()
    df.to_csv(os.path.join(out_dir, "odds_today.csv"), index=False)
    df.to_csv(os.path.join(out_dir, f"odds_{target}.csv"), index=False)


def status_payload(source: str, rows: int, target: str, notes: str) -> Dict[str, Any]:
    return {
        "status": "ok" if rows else "empty",
        "target_date": target,
        "selected_source": source,
        "rows": int(rows),
        "notes": notes,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_priority": ["manual", "current_file", "cache_exact", "cache_last_known", "empty"],
        "api_usage_policy": "The Odds API is optional/manual only to conserve credits.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--manual", default="data/manual/wnba_manual_odds.csv")
    args = ap.parse_args()

    target = args.date
    checks = [
        ("manual", normalize_manual(args.manual, target), "Loaded from manual odds file."),
        ("current_file", current_odds(args.raw, target), "Loaded from existing current odds file."),
        ("cache", cached_odds(args.raw, target), "Loaded from historical/cache odds."),
    ]

    selected_source = "empty"
    selected_df = empty_df()
    notes = "No odds source available."
    for source, df, note in checks:
        if not df.empty:
            selected_source, selected_df, notes = source, df, note
            break

    save(selected_df, target, args.raw)
    status = status_payload(selected_source, len(selected_df), target, notes)
    with open(os.path.join(args.raw, "odds_source_status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)

    print(json.dumps(status, indent=2))
    print(f"✅ Odds source manager complete: {selected_source} ({len(selected_df)} rows)")


if __name__ == "__main__":
    main()
