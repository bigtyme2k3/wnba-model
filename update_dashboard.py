"""
update_dashboard.py
-------------------
Auto-patches the dashboard JSX file with today's fresh pipeline JSON.
Run after daily_runner.py to keep the dashboard current without
manually copy-pasting JSON.

Usage:
    python update_dashboard.py
    python update_dashboard.py --date 2026-05-12
    python update_dashboard.py --predictions path/to/predictions.json --dashboard path/to/dashboard.jsx
"""

import re, json, argparse, os
from datetime import date

DEFAULT_DASHBOARD   = os.path.join(os.path.dirname(__file__), "dashboard/wnba_dashboard.jsx")
DEFAULT_PREDICTIONS = None  # Auto-finds latest in predictions/


def find_latest_predictions(pred_dir="predictions"):
    files = sorted([f for f in os.listdir(pred_dir) if f.startswith("predictions_") and f.endswith(".json")])
    if not files:
        raise FileNotFoundError(f"No prediction files found in {pred_dir}/")
    return os.path.join(pred_dir, files[-1])


def patch_dashboard(pred_path: str, dash_path: str) -> bool:
    """Replace the PIPELINE_DATA constant in the dashboard JSX."""
    if not os.path.exists(dash_path):
        print(f"  [ERROR] Dashboard not found: {dash_path}")
        return False

    with open(pred_path) as f:
        data = json.load(f)

    # Compact JSON — no extra whitespace
    new_json = json.dumps(data, separators=(",", ":"))

    with open(dash_path) as f:
        content = f.read()

    # Match: const PIPELINE_DATA = {...};
    pattern = r'(const PIPELINE_DATA\s*=\s*)(\{.*?\});'
    new_content, n = re.subn(pattern, rf'\g<1>{new_json};', content, flags=re.DOTALL)

    if n == 0:
        print("  [ERROR] Could not find PIPELINE_DATA in dashboard. Check the JSX file.")
        return False

    with open(dash_path, "w") as f:
        f.write(new_content)

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",        default=str(date.today()))
    parser.add_argument("--predictions", default=None)
    parser.add_argument("--dashboard",   default=DEFAULT_DASHBOARD)
    args = parser.parse_args()

    pred_path = args.predictions or os.path.join(
        "predictions", f"predictions_{args.date}.json"
    )
    if not os.path.exists(pred_path):
        print(f"  Prediction file not found: {pred_path}")
        print(f"  Searching for latest...")
        pred_path = find_latest_predictions()
        print(f"  Using: {pred_path}")

    with open(pred_path) as f:
        data = json.load(f)

    print(f"\n  Prediction date:  {data['date']}")
    print(f"  Games:            {len(data['games'])}")
    print(f"  Best bets:        {len(data['best_bets'])}")
    print(f"  High conf plays:  {sum(1 for b in data['best_bets'] if b['stars'] == 3)}")
    print(f"  Dashboard path:   {args.dashboard}")

    if not os.path.exists(args.dashboard):
        print(f"\n  [WARN] Dashboard JSX not found at {args.dashboard}")
        print(f"  Copy the dashboard from the Claude outputs folder first.")
        print(f"\n  JSON preview (paste into PIPELINE_DATA manually):")
        print(f"  {json.dumps(data, separators=(',',':'))[:200]}...")
        return

    success = patch_dashboard(pred_path, args.dashboard)
    if success:
        print(f"\n✅ Dashboard updated → {args.dashboard}")
        print(f"   Refresh the dashboard to see today's predictions.")
    else:
        print("\n❌ Auto-patch failed — paste JSON manually into PIPELINE_DATA")


if __name__ == "__main__":
    main()
