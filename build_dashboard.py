"""
build_dashboard.py
------------------
Reads the latest predictions JSON from the predictions/ folder and bakes it
into docs/index.html for a zero-dependency GitHub Pages dashboard.

Also merges data/raw/player_points_YYYY-MM-DD.csv when present so the Props tab
can render even if player points were generated outside daily_runner.py.
"""

import glob
import json
import os
import re
from datetime import date

import pandas as pd

PREDICTIONS_DIR = "predictions"
RAW_DIR = "data/raw"
OUTPUT_HTML = "docs/index.html"


def empty_dashboard_data():
    today = str(date.today())
    return {
        "date": today,
        "generated": None,
        "games": [],
        "best_bets": [],
        "player_points": [],
        "props_board": [],
        "data_health": {
            "odds": "missing",
            "props": "missing",
            "player_points": "missing",
            "spreads_found": 0,
            "totals_found": 0,
            "props_found": 0,
            "player_points_found": 0,
            "games": 0,
            "actionable_bets": 0,
            "high_bets": 0,
            "last_updated_utc": None,
        },
        "record": {"overall": "0-0", "win_pct": 0, "total_bets": 0, "by_type": {}, "by_conf": {}, "recent_10": []},
        "model_stats": {
            "spread": {"algo": "Ridge v2", "cv_mae": 9.72, "dir_acc": 0.716, "strong_ats": 0.815, "n": 0},
            "totals": {"algo": "Random Forest", "cv_mae": 6.77, "ou_acc": 0.542, "strong_ou": 0.554, "n": 0},
            "props": {"algo": "Ridge", "cv_mae": 6.00, "hit_rate": 0.721, "strong_hr": 0.754, "n": 0},
        },
    }


def find_predictions():
    today = str(date.today())
    candidates = [
        os.path.join(PREDICTIONS_DIR, f"predictions_{today}.json"),
    ] + sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")), reverse=True)

    seen = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            print(f"  Loaded: {path} ({len(data.get('games', []))} games)")
            return data

    print("  [WARN] No predictions file found — using empty data")
    return empty_dashboard_data()


def csv_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def load_player_points_for_date(target_date):
    candidates = [
        os.path.join(RAW_DIR, f"player_points_{target_date}.csv"),
        os.path.join(RAW_DIR, "player_points_today.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                print(f"  Loaded player points: {path} ({len(df)} rows)")
                rows = []
                for _, row in df.iterrows():
                    rows.append({k: csv_value(v) for k, v in row.to_dict().items()})
                return rows
            except Exception as exc:
                print(f"  [WARN] Could not load player points from {path}: {exc}")
    return []


def enrich_with_player_points(data):
    target_date = data.get("date") or str(date.today())
    points = data.get("player_points") or load_player_points_for_date(target_date)
    if not points:
        data.setdefault("player_points", [])
        data.setdefault("props_board", data.get("props_board", []))
        data.setdefault("data_health", {})["player_points"] = data.get("data_health", {}).get("player_points", "missing")
        data.setdefault("data_health", {})["player_points_found"] = 0
        return data

    data["player_points"] = points
    data["props_board"] = data.get("props_board") or points
    health = data.setdefault("data_health", {})
    health["player_points"] = "loaded"
    health["player_points_found"] = len(points)
    health["props_found"] = max(int(health.get("props_found", 0) or 0), len(data.get("props_board", [])))
    return data


def build_html(data):
    data = enrich_with_player_points(data)
    data_json = json.dumps(data, separators=(",", ":"))

    with open(OUTPUT_HTML) as f:
        html = f.read()

    pattern = r"const\s+DATA\s*=\s*.*?;\s*(?=\n\s*const|\n\s*let|\n\s*function|\n\s*window\.)"
    replacement = f"const DATA = {data_json};\n"
    new_html = re.sub(pattern, replacement, html, flags=re.DOTALL)

    if new_html == html:
        print("  [WARN] Could not find DATA constant to replace — check docs/index.html")
        return False

    with open(OUTPUT_HTML, "w") as f:
        f.write(new_html)
    return True


def main():
    print("\n═══ Building Dashboard ═══\n")
    os.makedirs("docs", exist_ok=True)

    data = find_predictions()
    success = build_html(data)

    if success:
        health = data.get("data_health", {})
        print(f"  ✅ {OUTPUT_HTML} updated")
        print(f"     Date: {data.get('date')}")
        print(f"     Games: {len(data.get('games', []))}")
        print(f"     Best bets: {len(data.get('best_bets', []))}")
        print(f"     Player points: {health.get('player_points_found', 0)}")
        print(f"     Odds: {health.get('odds', 'unknown')}")
    else:
        raise SystemExit("  ❌ Build failed")


if __name__ == "__main__":
    main()
