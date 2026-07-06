"""
projection_accuracy.py
----------------------
Prediction Accuracy Initiative.

Builds an audit layer for WNBA player props using whatever completed-result data
is already available in the repository. This script is defensive: if no final
results are available yet, it still writes a dashboard-ready empty-state report.

Adds `projection_accuracy` to predictions/predictions_YYYY-MM-DD.json and exports:
  - data/intelligence/projection_accuracy_YYYY-MM-DD.json
  - data/dashboard/projection_accuracy.json

No API calls. GitHub Pages compatible.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from glob import glob
from typing import Any, Dict, Iterable, List, Optional, Tuple

PRED_DIR = "predictions"
OUT_INTEL = "data/intelligence"
OUT_DASH = "data/dashboard"
HISTORY_DIR = "data/history"
TRACKING_DIR = "data/tracking"
RAW_DIR = "data/raw"

STAT_ALIASES = {
    "PTS": ["PTS", "points", "points_actual"],
    "REB": ["REB", "TRB", "rebounds", "rebounds_actual"],
    "AST": ["AST", "assists", "assists_actual"],
    "3PM": ["3PM", "FG3M", "3P", "three_pointers", "threes", "3pm_actual"],
    "PRA": ["PRA", "points_rebounds_assists", "pra_actual"],
    "PR": ["PR", "points_rebounds", "pr_actual"],
    "PA": ["PA", "points_assists", "pa_actual"],
    "RA": ["RA", "rebounds_assists", "ra_actual"],
}


def f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def load_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def norm_name(s: Any) -> str:
    return " ".join(str(s or "").lower().replace(".", "").replace("'", "").split())


def norm_stat(s: Any) -> str:
    raw = str(s or "").upper().replace(" ", "")
    mapping = {
        "POINTS": "PTS", "REBOUNDS": "REB", "ASSISTS": "AST", "THREES": "3PM",
        "3PTM": "3PM", "FG3M": "3PM", "PTS+REB+AST": "PRA", "PRA": "PRA",
        "PTS+REB": "PR", "PTS+AST": "PA", "REB+AST": "RA",
    }
    return mapping.get(raw, raw)


def grade_error(abs_error: float, stat: str) -> str:
    stat = norm_stat(stat)
    bands = {
        "PTS": (1.5, 3.0, 5.0),
        "REB": (0.8, 1.8, 3.0),
        "AST": (0.8, 1.8, 3.0),
        "3PM": (0.4, 0.9, 1.5),
        "PRA": (2.5, 5.0, 8.0),
        "PR": (2.0, 4.0, 6.5),
        "PA": (2.0, 4.0, 6.5),
        "RA": (1.5, 3.0, 5.0),
    }
    a, b, c = bands.get(stat, (1.5, 3.0, 5.0))
    if abs_error <= a:
        return "A"
    if abs_error <= b:
        return "B"
    if abs_error <= c:
        return "C"
    return "D"


def side_hit(signal: str, actual: float, line: float) -> Optional[bool]:
    sig = str(signal or "").upper()
    if sig in {"OVER", "YES"}:
        return actual > line
    if sig in {"UNDER", "NO"}:
        return actual < line
    return None


def stat_value(row: Dict[str, Any], stat: str) -> Optional[float]:
    stat = norm_stat(stat)
    aliases = STAT_ALIASES.get(stat, [stat])
    for key in aliases:
        if key in row and row[key] not in [None, "", "—"]:
            return f(row[key])
    pts = f(row.get("PTS", row.get("points", 0)))
    reb = f(row.get("REB", row.get("TRB", row.get("rebounds", 0))))
    ast = f(row.get("AST", row.get("assists", 0)))
    if stat == "PRA":
        return pts + reb + ast
    if stat == "PR":
        return pts + reb
    if stat == "PA":
        return pts + ast
    if stat == "RA":
        return reb + ast
    return None


def collect_actual_rows(target_date: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Return {(player, game/date-ish): stat row}. Handles many likely formats."""
    candidates = []
    candidates += glob(os.path.join(HISTORY_DIR, "*.json"))
    candidates += glob(os.path.join(TRACKING_DIR, "*.json"))
    candidates += glob(os.path.join(RAW_DIR, f"*{target_date}*box*.json"))
    candidates += glob(os.path.join(RAW_DIR, f"*{target_date}*score*.json"))
    candidates += glob(os.path.join(RAW_DIR, f"*{target_date}*result*.json"))
    rows: List[Dict[str, Any]] = []
    for path in candidates:
        data = load_json(path, None)
        if data is None:
            continue
        if isinstance(data, list):
            rows.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict):
            for key in ["player_stats", "boxscores", "results", "bets", "props", "rows", "data"]:
                val = data.get(key)
                if isinstance(val, list):
                    rows.extend([x for x in val if isinstance(x, dict)])
            # Some tracking files may be dict keyed by player.
            for k, v in data.items():
                if isinstance(v, dict) and any(stat in v for stat in ["PTS", "points", "actual"]):
                    tmp = dict(v)
                    tmp.setdefault("player", k)
                    rows.append(tmp)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        player = norm_name(r.get("player") or r.get("name") or r.get("athlete") or r.get("player_name"))
        if not player:
            continue
        game = str(r.get("game") or r.get("matchup") or r.get("date") or target_date)
        # Only keep plausible rows for target date when date exists.
        if r.get("date") and target_date not in str(r.get("date")):
            continue
        out[(player, game.lower())] = r
        out[(player, target_date)] = r
    return out


def find_actual(prop: Dict[str, Any], actual_rows: Dict[Tuple[str, str], Dict[str, Any]], target_date: str) -> Optional[float]:
    player = norm_name(prop.get("player"))
    game = str(prop.get("game") or "").lower()
    stat = norm_stat(prop.get("stat"))
    for key in [(player, game), (player, target_date)]:
        if key in actual_rows:
            val = stat_value(actual_rows[key], stat)
            if val is not None:
                return val
    # Last resort: match player only.
    for (p, _), row in actual_rows.items():
        if p == player:
            val = stat_value(row, stat)
            if val is not None:
                return val
    # If prediction row already has actual result, use it.
    for k in ["actual", "result_value", "final", "actual_value"]:
        if k in prop and prop[k] not in [None, "", "—"]:
            return f(prop[k])
    return None


def diagnose_miss(prop: Dict[str, Any], actual: float, pred: float, hit: Optional[bool]) -> List[str]:
    reasons = []
    line = f(prop.get("line"))
    stat = norm_stat(prop.get("stat"))
    err = actual - pred
    if hit is False:
        if abs(err) <= 1 and stat in {"REB", "AST", "3PM"}:
            reasons.append("Projection was close; line margin decided result")
        elif abs(err) <= 2.5:
            reasons.append("Projection was close; normal variance")
        elif err < 0:
            reasons.append("Actual finished below projection")
        else:
            reasons.append("Actual finished above projection")
    if str(prop.get("injury_status", "ACTIVE")).upper() not in {"", "ACTIVE", "PROBABLE"}:
        reasons.append("Injury status added uncertainty")
    if f(prop.get("readiness_score"), 100) < 70:
        reasons.append("Low readiness signal")
    if f(prop.get("opp_rank"), 8) <= 5:
        reasons.append("Difficult opponent rank")
    if f(prop.get("projected_minutes")) <= 0:
        reasons.append("Minutes projection unavailable")
    if line and abs(pred - line) < 1:
        reasons.append("Thin edge versus line")
    return reasons[:5]


def build_accuracy_report(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    actual_rows = collect_actual_rows(target_date)
    audits = []
    for p in props:
        pred = f(p.get("pred", p.get("projection", 0)))
        if not pred:
            continue
        actual = find_actual(p, actual_rows, target_date)
        if actual is None:
            continue
        stat = norm_stat(p.get("stat"))
        line = f(p.get("line"))
        error = round(actual - pred, 2)
        abs_error = round(abs(error), 2)
        hit = side_hit(str(p.get("signal")), actual, line) if line else None
        audit = {
            "player": p.get("player"),
            "team": p.get("team"),
            "game": p.get("game"),
            "stat": stat,
            "line": p.get("line"),
            "signal": p.get("signal"),
            "projection": round(pred, 2),
            "actual": round(actual, 2),
            "error": error,
            "abs_error": abs_error,
            "hit": hit,
            "grade": grade_error(abs_error, stat),
            "ups_score": p.get("ups_score"),
            "confidence": p.get("confidence_v2", p.get("score")),
            "readiness_score": p.get("readiness_score"),
            "miss_reasons": diagnose_miss(p, actual, pred, hit),
        }
        audits.append(audit)
    audits.sort(key=lambda x: x["abs_error"], reverse=True)

    by_stat = defaultdict(list)
    by_player = defaultdict(list)
    by_grade = Counter()
    misses = []
    hits = 0
    graded = 0
    for a in audits:
        by_stat[a["stat"]].append(a)
        by_player[str(a.get("player") or "Unknown")].append(a)
        by_grade[a["grade"]] += 1
        if a.get("hit") is not None:
            graded += 1
            if a.get("hit"):
                hits += 1
            else:
                misses.append(a)

    def summarize(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        rows = list(rows)
        if not rows:
            return {"count": 0, "mae": None, "bias": None, "hit_rate": None}
        known = [r for r in rows if r.get("hit") is not None]
        return {
            "count": len(rows),
            "mae": round(sum(f(r.get("abs_error")) for r in rows) / len(rows), 2),
            "bias": round(sum(f(r.get("error")) for r in rows) / len(rows), 2),
            "hit_rate": round(sum(1 for r in known if r.get("hit")) / len(known) * 100, 1) if known else None,
        }

    stat_summary = {k: summarize(v) for k, v in by_stat.items()}
    player_summary = sorted(
        [{"player": k, **summarize(v)} for k, v in by_player.items() if len(v) >= 1],
        key=lambda x: (x.get("mae") if x.get("mae") is not None else 999),
    )[:25]
    worst_misses = sorted(misses, key=lambda x: f(x.get("abs_error")), reverse=True)[:15]
    best_calls = sorted([a for a in audits if a.get("hit")], key=lambda x: f(x.get("abs_error")))[:15]

    if audits:
        overall_mae = round(sum(f(a.get("abs_error")) for a in audits) / len(audits), 2)
        overall_bias = round(sum(f(a.get("error")) for a in audits) / len(audits), 2)
    else:
        overall_mae = None
        overall_bias = None

    lessons = []
    if overall_bias is not None:
        if overall_bias > 1:
            lessons.append("Model under-projected actual results on average; review pace/usage assumptions.")
        elif overall_bias < -1:
            lessons.append("Model over-projected actual results on average; review minutes/blowout assumptions.")
        else:
            lessons.append("Projection bias is controlled; focus on reducing player-level variance.")
    if worst_misses:
        common = Counter(r for m in worst_misses for r in m.get("miss_reasons", [])).most_common(3)
        lessons.extend([f"Common miss factor: {label}." for label, _ in common])
    if not audits:
        lessons.append("No completed prop results found yet. Report will populate after box scores/results are available.")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "audited_props": len(audits),
            "graded_bets": graded,
            "hit_rate": round(hits / graded * 100, 1) if graded else None,
            "mae": overall_mae,
            "bias": overall_bias,
            "grade_counts": dict(by_grade),
            "actual_rows_available": len(actual_rows),
        },
        "lessons": lessons[:8],
        "stat_summary": stat_summary,
        "player_summary": player_summary,
        "worst_misses": worst_misses,
        "best_calls": best_calls,
        "audits": audits[:200],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    pred_path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(pred_path):
        raise SystemExit(f"Missing predictions file: {pred_path}")
    data = load_json(pred_path, {})
    report = build_accuracy_report(data, args.date)
    data["projection_accuracy"] = report
    with open(pred_path, "w") as fh:
        json.dump(data, fh, indent=2)
    os.makedirs(OUT_INTEL, exist_ok=True)
    os.makedirs(OUT_DASH, exist_ok=True)
    with open(os.path.join(OUT_INTEL, f"projection_accuracy_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_DASH, "projection_accuracy.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ Projection Accuracy built: {report['summary']['audited_props']} audited props")


if __name__ == "__main__":
    main()
