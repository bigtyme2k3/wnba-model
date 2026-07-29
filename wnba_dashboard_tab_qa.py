"""Validate that each production dashboard tab is present and wired to data markers."""
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
    "Games": ["Games Today", "window.marketsV25", "namedCandidates"],
    "Player Props": ["function actualHistory", "function wirePropFilters", "setPropSort"],
    "Top Plays": ["Best Bets Shortlist", "active ranked plays", "finalKeys.has(k)"],
    "Market Intelligence": ["v4-market-intelligence-script"],
    "Mission Control": ["v4-mission-control-script"],
    "Learning": ["window.WNBA_RESULTS_DATA"],
    "Performance": ["v4-projection-performance-script", "Results & Grading"],
    "Explainability": ["v4-explainability-script"],
    "Alt Markets": ["v4-alt-streaks-script", "v4-alt-ladders-script", "Sportsbook ALT Ladders"],
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
        if row["missing_markers"]:
            for marker in row["missing_markers"]:
                print(f"  missing marker: {marker}")
        else:
            print("  all required markers present")
    print("=" * 72)
    print(json.dumps(result["summary"], indent=2))
    print(f"JSON report: {OUT_JSON.relative_to(ROOT)}")
    print(f"Markdown report: {OUT_MD.relative_to(ROOT)}")


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
        failed_tabs = ", ".join(row["tab"] for row in result["tabs"] if row["status"] == "red")
        raise SystemExit(f"Dashboard tab QA failed: {failed_tabs}")


if __name__ == "__main__":
    main()
