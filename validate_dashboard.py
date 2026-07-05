"""
validate_dashboard.py
---------------------
Lightweight sanity checks for the GitHub Pages dashboard after build_dashboard.py.

This does not judge betting quality. It catches broken HTML/data injection before the
workflow commits a bad dashboard.

Checks:
  - docs/index.html exists
  - const DATA = {...}; is present and valid JSON
  - DATA has games, best_bets, model_stats, and data_health keys
  - dashboard JavaScript placeholders were not left as an empty template when a
    predictions JSON exists

Usage:
  python validate_dashboard.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

HTML_PATH = "docs/index.html"
PREDICTIONS_DIR = "predictions"


def fail(message: str) -> int:
    print(f"❌ {message}")
    return 1


def warn(message: str):
    print(f"⚠️ {message}")


def main() -> int:
    if not os.path.exists(HTML_PATH):
        return fail(f"Missing dashboard file: {HTML_PATH}")

    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    match = re.search(r"const\s+DATA\s*=\s*(\{.*?\});", html, flags=re.DOTALL)
    if not match:
        return fail("Could not find const DATA = {...}; in docs/index.html")

    try:
        data = json.loads(match.group(1))
    except Exception as exc:
        return fail(f"Dashboard DATA JSON is invalid: {exc}")

    required = ["games", "best_bets", "model_stats", "data_health"]
    missing = [k for k in required if k not in data]
    if missing:
        return fail(f"Dashboard DATA missing keys: {missing}")

    if not isinstance(data.get("games"), list):
        return fail("DATA.games is not a list")
    if not isinstance(data.get("best_bets"), list):
        return fail("DATA.best_bets is not a list")
    if not isinstance(data.get("data_health"), dict):
        return fail("DATA.data_health is not a dict")

    pred_files = sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")))
    if pred_files and not data.get("date"):
        return fail("Predictions exist, but dashboard DATA.date is empty")

    health = data.get("data_health", {})
    games = len(data.get("games", []))
    bets = len(data.get("best_bets", []))
    props = len(data.get("props", data.get("player_points", [])) or [])

    if health.get("odds") != "loaded":
        warn("Odds not marked loaded in dashboard health")
    if props == 0:
        warn("No props rows in dashboard. This can be normal if player props are not posted yet.")

    print("✅ Dashboard sanity check passed")
    print(f"   Games: {games}")
    print(f"   Best bets: {bets}")
    print(f"   Props rows: {props}")
    print(f"   Date: {data.get('date')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
