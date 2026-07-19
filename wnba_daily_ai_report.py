"""Generate a concise daily WNBA betting research briefing from warehouse intelligence.

The report is descriptive research only. It suppresses stale games and does not label
signals as guaranteed picks.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

INTELLIGENCE = Path("data/dashboard/wnba_betting_intelligence.json")
OUT_JSON = Path("data/dashboard/wnba_daily_ai_report.json")
OUT_MD = Path("data/dashboard/wnba_daily_ai_report.md")
WAREHOUSE_JSON = Path("data/warehouse/wnba_daily_ai_report.json")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def confidence(score: float, matches: int) -> str:
    if matches >= 4 and score >= 30:
        return "high-research-interest"
    if matches >= 2 and score >= 10:
        return "medium-research-interest"
    return "low-research-interest"


def build(source: Path = INTELLIGENCE, horizon_hours: int = 72) -> dict[str, Any]:
    if not source.exists():
        raise SystemExit(f"Intelligence file not found: {source}")
    intel = json.loads(source.read_text(encoding="utf-8"))
    generated = now_utc()
    cutoff = generated + timedelta(hours=horizon_hours)

    valid = []
    stale = 0
    beyond = 0
    for item in intel.get("opportunity_scanner", []):
        tip = parse_dt(item["commence_time_utc"])
        if tip < generated:
            stale += 1
            continue
        if tip > cutoff:
            beyond += 1
            continue
        angles = item.get("matched_angles", [])
        valid.append({
            **item,
            "matched_angle_count": len(angles),
            "confidence_label": confidence(float(item.get("signal_score") or 0), len(angles)),
            "top_reasons": [
                {
                    "market": a.get("market"),
                    "dimension": a.get("dimension"),
                    "value": a.get("value"),
                    "record": f"{a.get('wins', 0)}-{a.get('losses', 0)}-{a.get('pushes', 0)}",
                    "win_pct": a.get("win_pct"),
                    "estimated_roi_minus_110": a.get("roi_at_minus_110"),
                    "sample": a.get("graded"),
                }
                for a in angles[:5]
            ],
        })

    valid.sort(key=lambda x: (x.get("signal_score", 0), x.get("matched_angle_count", 0)), reverse=True)
    grouped: dict[str, dict[str, Any]] = {}
    for item in valid:
        key = item["game_id"]
        game = grouped.setdefault(key, {
            "game_id": key,
            "commence_time_utc": item["commence_time_utc"],
            "signals": [],
        })
        game["signals"].append(item)
    games = sorted(grouped.values(), key=lambda x: x["commence_time_utc"])

    top_trends = [t for t in intel.get("trend_discovery", []) if (t.get("graded") or 0) >= 20][:10]
    payload = {
        "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
        "status": "slate_available" if games else "no_current_slate",
        "horizon_hours": horizon_hours,
        "summary": {
            "games_in_report": len(games),
            "signals_in_report": len(valid),
            "stale_signals_suppressed": stale,
            "signals_beyond_horizon": beyond,
            "source_trends": intel.get("summary", {}).get("discovered_trends", 0),
        },
        "top_signals": valid[:15],
        "games": games,
        "market_research_watchlist": top_trends,
        "guardrails": [
            "Signals are historical matches, not guaranteed predictions.",
            "Do not combine overlapping angles as independent evidence.",
            "Confirm injuries, rest, and current sportsbook prices before wagering.",
            "Use flat stakes for evaluation; martingale progression is not recommended.",
        ],
    }

    lines = ["# WNBA Daily AI Research Report", "", f"Generated: {payload['generated_at_utc']}", ""]
    if not games:
        lines += ["## No current slate signals", "", "No future opportunities were found inside the selected time horizon. Stale warehouse signals were suppressed.", ""]
    else:
        lines += [f"## Slate summary", "", f"- {len(games)} games", f"- {len(valid)} team/book signals", ""]
        for game in games:
            lines += [f"## Game — {game['commence_time_utc']}", ""]
            for s in game["signals"]:
                lines += [
                    f"### {s['team']} {s['spread']:+g} ({s['bookmaker_key']})",
                    f"Research level: **{s['confidence_label']}** | score {s['signal_score']} | {s['matched_angle_count']} matched angles",
                    "",
                ]
                for r in s["top_reasons"][:3]:
                    lines.append(f"- {r['value']}: {r['record']} ({r['win_pct']}%, n={r['sample']})")
                lines.append("")
    lines += ["## Guardrails", ""] + [f"- {x}" for x in payload["guardrails"]] + [""]

    for path in (OUT_JSON, WAREHOUSE_JSON):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=INTELLIGENCE)
    ap.add_argument("--horizon-hours", type=int, default=72)
    args = ap.parse_args()
    build(args.source, args.horizon_hours)


if __name__ == "__main__":
    main()
