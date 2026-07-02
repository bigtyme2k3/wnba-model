"""
build_dashboard.py
------------------
Reads today's predictions JSON from the predictions/ folder
and bakes it directly into docs/index.html.

Run automatically by GitHub Actions after daily_runner.py.
Usage: python build_dashboard.py
"""

import os, json, glob
from datetime import date

PREDICTIONS_DIR = "predictions"
OUTPUT_HTML     = "docs/index.html"

# ── Find latest predictions file ──────────────────────────────────────────────
def find_predictions():
    today = str(date.today())
    # Try today first, then fall back to most recent
    candidates = [
        os.path.join(PREDICTIONS_DIR, f"predictions_{today}.json"),
    ] + sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")), reverse=True)

    for path in candidates:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            print(f"  Loaded: {path} ({len(data.get('games',[]))} games)")
            return data

    print("  [WARN] No predictions file found — using empty data")
    return {"date": today, "games": [], "best_bets": [],
            "model_stats": {"spread":{"algo":"Ridge v2","cv_mae":9.72,"dir_acc":0.716,"strong_ats":0.815,"n":0},
                            "totals":{"algo":"Random Forest","cv_mae":6.77,"ou_acc":0.542,"strong_ou":0.554,"n":0},
                            "props": {"algo":"Ridge","cv_mae":6.00,"hit_rate":0.721,"strong_hr":0.754,"n":0}}}

# ── Build HTML ─────────────────────────────────────────────────────────────────
def build_html(data):
    data_json = json.dumps(data, separators=(',', ':'))

    with open("docs/index.html") as f:
        html = f.read()

    # Replace the DATA constant with real data
    import re
    new_html = re.sub(
        r'const DATA = \{.*?\};',
        f'const DATA = {data_json};',
        html,
        flags=re.DOTALL
    )

    if new_html == html:
        print("  [WARN] Could not find DATA constant to replace — check index.html")
        return False

    with open("docs/index.html", "w") as f:
        f.write(new_html)
    return True


def main():
    print("\n═══ Building Dashboard ═══\n")
    os.makedirs("docs", exist_ok=True)

    data    = find_predictions()
    success = build_html(data)

    if success:
        print(f"  ✅ docs/index.html updated")
        print(f"     Date: {data['date']}")
        print(f"     Games: {len(data.get('games',[]))}")
        print(f"     Best bets: {len(data.get('best_bets',[]))}")
    else:
        print("  ❌ Build failed")

if __name__ == "__main__":
    main()
