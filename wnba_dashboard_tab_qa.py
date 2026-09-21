"""Validate every routed production dashboard tab is present and callable.

This audit mirrors the 13-tab locked router in patch_dashboard_v4_ui_freeze.py.
A tab passes when its navigation entry and its route/renderer markers are in the
built Pages artifact. Empty current data is allowed; a missing route is not.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "docs" / "index.html"
OUT_JSON = ROOT / "data" / "dashboard" / "wnba_dashboard_tab_qa.json"
OUT_MD = ROOT / "docs" / "DASHBOARD_TAB_QA_REPORT.md"

TAB_CHECKS = {
    "Games": ["['games','Games']", "gamesV25"],
    "Game Performance": ["['game-performance','Game Performance']", "fullGamePerformance"],
    "Matchups": ["['matchups','Matchups']", "canonicalMatchups"],
    "Player Props": ["['props','Player Props']", "WNBA_CANONICAL_PROPS"],
    "ALT Props": ["['alt-props','ALT Props']", "canonicalAltProps"],
    "Sportsbooks": ["['sportsbooks','Sportsbooks']", "canonicalSportsbooks"],
    "Best Bets": ["['best','Best Bets']", "canonicalBest"],
    "AI Center": ["['ai','AI Center']", "canonicalAI"],
    "Live": ["['live','Live']", "canonicalLive"],
    "Remaining Season": ["['remaining','Remaining Season']", "remainingSeason"],
    "Results": ["['results','Results']", "s19-m06-results-script", "Player Props Results"],
    "Portfolio": ["['portfolio','Portfolio']", "canonicalPortfolio"],
    "Data Health": ["['health','Data Health']", "v5-current-data-health-script"],
}


def audit() -> dict:
    html = HTML.read_text(encoding="utf-8") if HTML.exists() else ""
    tabs = []
    for name, markers in TAB_CHECKS.items():
        missing = [marker for marker in markers if marker not in html]
        tabs.append({
            "tab": name,
            "status": "green" if not missing else "red",
            "required_markers": markers,
            "missing_markers": missing,
        })
    red = sum(row["status"] == "red" for row in tabs)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "red" if red else "green",
        "summary": {
            "tabs": len(tabs),
            "passing": len(tabs) - red,
            "failing": red,
            "all_tabs_active": red == 0,
            "html_bytes": len(html),
        },
        "tabs": tabs,
    }


def write_report(result: dict) -> None:
    lines = [
        "# WNBA Dashboard Tab QA",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Overall status: **{result['status'].upper()}**",
        "",
        "| Tab | Status | Missing markers |",
        "|---|---|---|",
    ]
    for row in result["tabs"]:
        missing = ", ".join(row["missing_markers"]) or "None"
        lines.append(f"| {row['tab']} | {row['status'].upper()} | {missing} |")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_diagnostics(result: dict) -> None:
    print("Dashboard tab QA results")
    print("=" * 72)
    for row in result["tabs"]:
        status = "PASS" if row["status"] == "green" else "FAIL"
        print(f"{status}: {row['tab']}")
        for marker in row["missing_markers"]:
            print(f"  missing marker: {marker}")
    print("=" * 72)
    print(json.dumps(result["summary"], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = audit()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_report(result)
    print_diagnostics(result)
    if args.strict and result["status"] == "red":
        failed = ", ".join(row["tab"] for row in result["tabs"] if row["status"] == "red")
        raise SystemExit(f"Dashboard tab QA failed: {failed}")


if __name__ == "__main__":
    main()
