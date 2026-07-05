"""
model_tracking.py
-----------------
Builds an enhanced model-tracking report for the dashboard.

This is model-performance tracking, not bankroll tracking.
It summarizes graded bets plus today's data health into:
  - overall performance
  - market/stat performance
  - confidence/grade performance
  - sportsbook comparison
  - player and team performance
  - model health

Output:
  data/tracking/model_tracking.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone

import pandas as pd

TRACKING_DIR = "data/tracking"
GRADED_PATH = os.path.join(TRACKING_DIR, "graded_bets.csv")
OUT_PATH = os.path.join(TRACKING_DIR, "model_tracking.json")
RAW_DIR = "data/raw"


def safe_float(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def safe_int(v, default=0):
    try:
        if pd.isna(v):
            return default
        return int(v)
    except Exception:
        return default


def empty_summary(target_date):
    return {
        "date": target_date,
        "overall": "0-0-0",
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "bets": 0,
        "win_pct": 0,
        "roi": 0,
        "profit_units": 0,
        "clv_avg": 0,
        "avg_ev": 0,
        "avg_edge": 0,
        "by_type": {},
        "by_stat": {},
        "by_conf": {},
        "by_grade": {},
        "by_book": {},
        "by_player": {},
        "by_team": {},
        "recent_10": [],
        "model_health": {},
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
    }


def record_block(df):
    if df.empty:
        return {"bets": 0, "record": "0-0-0", "win_pct": 0, "roi": 0, "units": 0, "avg_ev": 0, "avg_clv": 0, "avg_edge": 0}
    wins = int((df.get("result", pd.Series(dtype=str)) == "WIN").sum())
    losses = int((df.get("result", pd.Series(dtype=str)) == "LOSS").sum())
    pushes = int((df.get("result", pd.Series(dtype=str)) == "PUSH").sum())
    graded = wins + losses
    units = round(float(df.get("profit_units", pd.Series(dtype=float)).fillna(0).sum()), 2)
    return {
        "bets": int(len(df)),
        "record": f"{wins}-{losses}-{pushes}",
        "win_pct": round(wins / graded, 3) if graded else 0,
        "roi": round(units / max(1, len(df)), 3),
        "units": units,
        "avg_ev": round(float(df.get("ev_pct", pd.Series(dtype=float)).fillna(0).mean()), 2) if "ev_pct" in df else 0,
        "avg_clv": round(float(df.get("clv", pd.Series(dtype=float)).fillna(0).mean()), 2) if "clv" in df else 0,
        "avg_edge": round(float(df.get("edge", pd.Series(dtype=float)).fillna(0).mean()), 2) if "edge" in df else 0,
    }


def group_summary(df, col, limit=20):
    if df.empty or col not in df.columns:
        return {}
    out = {}
    for key, group in df.groupby(col, dropna=False):
        if pd.isna(key) or str(key).strip() == "":
            key = "Unknown"
        out[str(key)] = record_block(group)
    return dict(sorted(out.items(), key=lambda kv: (-kv[1].get("bets", 0), kv[0]))[:limit])


def load_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def health_status(target_date):
    files = {
        "odds": [os.path.join(RAW_DIR, f"odds_{target_date}.csv"), os.path.join(RAW_DIR, "odds_today.csv")],
        "props": [os.path.join(RAW_DIR, f"props_raw_{target_date}.csv"), os.path.join(RAW_DIR, "props_today.csv")],
        "player_points": [os.path.join(RAW_DIR, f"player_points_{target_date}.csv"), os.path.join(RAW_DIR, "player_points_today.csv")],
        "injuries": [os.path.join(RAW_DIR, f"injuries_{target_date}.csv"), os.path.join(RAW_DIR, "injuries_today.csv")],
        "line_shopping": [os.path.join(RAW_DIR, f"line_shopping_best_{target_date}.csv"), os.path.join(RAW_DIR, "line_shopping_best_today.csv")],
    }
    health = {"target_date": target_date, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    for name, paths in files.items():
        path = next((p for p in paths if os.path.exists(p)), None)
        df = load_csv(path) if path else pd.DataFrame()
        health[name] = "loaded" if path and not df.empty else "empty" if path else "missing"
        health[f"{name}_rows"] = int(len(df)) if not df.empty else 0
        health[f"{name}_file"] = path or ""
    injuries = load_csv(next((p for p in files["injuries"] if os.path.exists(p)), ""))
    if not injuries.empty:
        health["injury_out_count"] = int((injuries.get("is_out", pd.Series(dtype=bool)).astype(str).str.lower().isin(["true", "1"])).sum()) if "is_out" in injuries else int(injuries.get("severity", pd.Series(dtype=str)).astype(str).str.upper().isin(["OUT", "DOUBTFUL"]).sum())
        health["injury_questionable_count"] = int(injuries.get("severity", pd.Series(dtype=str)).astype(str).str.upper().eq("QUESTIONABLE").sum()) if "severity" in injuries else 0
    else:
        health["injury_out_count"] = 0
        health["injury_questionable_count"] = 0
    return health


def build_summary(target_date):
    summary = empty_summary(target_date)
    df = load_csv(GRADED_PATH)
    if df.empty:
        summary["model_health"] = health_status(target_date)
        return summary

    overall = record_block(df)
    wins, losses, pushes = overall["record"].split("-")
    summary.update({
        "overall": overall["record"],
        "wins": safe_int(wins),
        "losses": safe_int(losses),
        "pushes": safe_int(pushes),
        "bets": overall["bets"],
        "win_pct": overall["win_pct"],
        "roi": overall["roi"],
        "profit_units": overall["units"],
        "clv_avg": overall["avg_clv"],
        "avg_ev": overall["avg_ev"],
        "avg_edge": overall["avg_edge"],
        "by_type": group_summary(df, "type"),
        "by_stat": group_summary(df, "stat"),
        "by_conf": group_summary(df, "conf"),
        "by_grade": group_summary(df, "grade"),
        "by_book": group_summary(df, "book" if "book" in df.columns else "best_book" if "best_book" in df.columns else "sportsbook"),
        "by_player": group_summary(df, "player", limit=25),
        "by_team": group_summary(df, "team", limit=25),
        "recent_10": df.tail(10).to_dict("records"),
        "model_health": health_status(target_date),
    })
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    summary = build_summary(args.date)
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"✅ Model tracking written → {args.out}")
    print(f"   Overall: {summary['overall']} | Bets: {summary.get('bets', 0)} | CLV: {summary.get('clv_avg', 0)}")


if __name__ == "__main__":
    main()
