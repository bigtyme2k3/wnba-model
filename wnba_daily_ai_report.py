"""Generate a concise daily WNBA betting research briefing from warehouse intelligence.

The report is descriptive research only. It suppresses stale games and does not label
signals as guaranteed picks.
"""
from __future__ import annotations

import argparse
import json
import math
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


def quality_grade(score: float) -> str:
    if score >= 80:
        return "Strong Research Play"
    if score >= 65:
        return "Lean"
    if score >= 50:
        return "Watch"
    return "Pass"


def bet_quality(item: dict[str, Any], best_spread: float | None) -> dict[str, Any]:
    angles = item.get("matched_angles", [])
    samples = [int(a.get("graded") or 0) for a in angles]
    wilsons = [float(a.get("wilson_low_pct") or 0) for a in angles]
    rois = [float(a.get("roi_at_minus_110") or 0) for a in angles]

    angle_count = len(angles)
    avg_sample = sum(samples) / angle_count if angle_count else 0.0
    avg_wilson = sum(wilsons) / angle_count if angle_count else 0.0
    avg_roi = sum(rois) / angle_count if angle_count else 0.0

    current_spread = item.get("spread")
    line_edge = 0.0
    if current_spread is not None and best_spread is not None:
        line_edge = max(0.0, float(best_spread) - float(current_spread))

    components = {
        "historical_confidence": min(35.0, max(0.0, (avg_wilson - 45.0) * 2.5)),
        "sample_size": min(20.0, 20.0 * math.log1p(avg_sample) / math.log1p(100.0)) if avg_sample else 0.0,
        "independent_angle_count": min(20.0, angle_count * 5.0),
        "estimated_roi": min(15.0, max(0.0, avg_roi * 0.4)),
        "line_shop_value": min(10.0, line_edge * 5.0),
    }
    total = round(sum(components.values()), 1)
    return {
        "score": total,
        "grade": quality_grade(total),
        "best_available_spread": best_spread,
        "line_shop_edge_points": round(line_edge, 1),
        "average_sample": round(avg_sample, 1),
        "average_wilson_low_pct": round(avg_wilson, 2),
        "average_estimated_roi_minus_110": round(avg_roi, 2),
        "components": {k: round(v, 1) for k, v in components.items()},
        "note": "Exploratory research grade, not a wager recommendation.",
    }


def build(source: Path = INTELLIGENCE, horizon_hours: int = 72) -> dict[str, Any]:
    if not source.exists():
        raise SystemExit(f"Intelligence file not found: {source}")
    intel = json.loads(source.read_text(encoding="utf-8"))
    generated = now_utc()
    cutoff = generated + timedelta(hours=horizon_hours)

    raw_valid = []
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
        raw_valid.append(item)

    best_lines: dict[tuple[str, str], float] = {}
    for item in raw_valid:
        if item.get("spread") is None:
            continue
        key = (item["game_id"], item["team"])
        best_lines[key] = max(best_lines.get(key, float("-inf")), float(item["spread"]))

    valid = []
    for item in raw_valid:
        angles = item.get("matched_angles", [])
        key = (item["game_id"], item["team"])
        quality = bet_quality(item, best_lines.get(key))
        valid.append({
            **item,
            "matched_angle_count": len(angles),
            "confidence_label": confidence(float(item.get("signal_score") or 0), len(angles)),
            "bet_quality": quality,
            "top_reasons": [
                {
                    "market": a.get("market"),
                    "dimension": a.get("dimension"),
                    "value": a.get("value"),
                    "record": f"{a.get('wins', 0)}-{a.get('losses', 0)}-{a.get('pushes', 0)}",
                    "win_pct": a.get("win_pct"),
                    "estimated_roi_minus_110": a.get("roi_at_minus_110"),
                    "sample": a.get("graded"),
                    "wilson_low_pct": a.get("wilson_low_pct"),
                }
                for a in angles[:5]
            ],
        })

    valid.sort(key=lambda x: (x["bet_quality"]["score"], x.get("signal_score", 0)), reverse=True)
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
    grade_counts = {grade: sum(s["bet_quality"]["grade"] == grade for s in valid) for grade in ("Strong Research Play", "Lean", "Watch", "Pass")}
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
            "quality_grades": grade_counts,
        },
        "top_signals": valid[:15],
        "games": games,
        "market_research_watchlist": top_trends,
        "quality_methodology": {
            "maximum_score": 100,
            "weights": {
                "historical_confidence": 35,
                "sample_size": 20,
                "independent_angle_count": 20,
                "estimated_roi": 15,
                "line_shop_value": 10,
            },
            "thresholds": {
                "Strong Research Play": 80,
                "Lean": 65,
                "Watch": 50,
                "Pass": 0,
            },
        },
        "guardrails": [
            "Quality grades are exploratory research labels, not guaranteed predictions.",
            "Do not combine overlapping angles as independent evidence.",
            "Confirm injuries, rest, and current sportsbook prices before wagering.",
            "Use flat stakes for evaluation; martingale progression is not recommended.",
        ],
    }

    lines = ["# WNBA Daily AI Research Report", "", f"Generated: {payload['generated_at_utc']}", ""]
    if not games:
        lines += ["## No current slate signals", "", "No future opportunities were found inside the selected time horizon. Stale warehouse signals were suppressed.", ""]
    else:
        lines += ["## Slate summary", "", f"- {len(games)} games", f"- {len(valid)} team/book signals", f"- Grades: {grade_counts}", ""]
        for game in games:
            lines += [f"## Game — {game['commence_time_utc']}", ""]
            for s in game["signals"]:
                q = s["bet_quality"]
                lines += [
                    f"### {s['team']} {s['spread']:+g} ({s['bookmaker_key']})",
                    f"Bet quality: **{q['grade']} — {q['score']}/100**",
                    f"Research level: **{s['confidence_label']}** | signal {s['signal_score']} | {s['matched_angle_count']} matched angles",
                    f"Best line: {q['best_available_spread']:+g} | line-shop edge: {q['line_shop_edge_points']:+g} points",
                    "",
                ]
                for r in s["top_reasons"][:3]:
                    lines.append(f"- {r['value']}: {r['record']} ({r['win_pct']}%, n={r['sample']}, Wilson floor {r['wilson_low_pct']}%)")
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
