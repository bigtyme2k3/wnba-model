"""
build_dashboard.py
------------------
Reads the latest predictions JSON from the predictions/ folder and bakes it
into docs/index.html for a zero-dependency GitHub Pages dashboard.
"""

import glob
import json
import os
import re
from datetime import date

PREDICTIONS_DIR = "predictions"
OUTPUT_HTML = "docs/index.html"


def empty_dashboard_data():
    today = str(date.today())
    return {
        "date": today,
        "generated": None,
        "games": [],
        "best_bets": [],
        "data_health": {
            "odds": "missing",
            "spreads_found": 0,
            "totals_found": 0,
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


def build_html(data):
    data_json = json.dumps(data, separators=(",", ":"))

    with open(OUTPUT_HTML) as f:
        html = f.read()

    # Replace any existing DATA assignment, including large minified JSON.
    pattern = r"const\s+DATA\s*=\s*.*?;\s*(?=\n\s*//|\n\s*const|\n\s*let|\n\s*function|\n\s*window\.)"
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
        print(f"     Odds: {health.get('odds', 'unknown')}")
    else:
        raise SystemExit("  ❌ Build failed")


if __name__ == "__main__":
    main()
