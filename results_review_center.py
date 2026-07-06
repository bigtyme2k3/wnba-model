"""
results_review_center.py
------------------------
WNBA Results Review Center.

Creates a daily review of yesterday/today completed recommendations:
- wins/losses/pushes when results are available
- profit/loss estimate
- hit rate
- biggest miss
- best call
- CLV/projection lessons
- model learning notes

This script is defensive: if final results are not available yet, it still
produces a dashboard-ready empty-state report.

Outputs:
  - data/dashboard/results_review_center.json
  - data/intelligence/results_review_center_YYYY-MM-DD.json
  - predictions/predictions_YYYY-MM-DD.json -> results_review_center
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from glob import glob
from typing import Any, Dict, List, Optional

PRED_DIR = "predictions"
OUT_DASH = "data/dashboard"
OUT_INTEL = "data/intelligence"


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
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def norm_name(v: Any) -> str:
    return " ".join(str(v or "").lower().replace(".", "").replace("'", "").split())


def norm_stat(v: Any) -> str:
    raw = str(v or "").upper().replace(" ", "")
    return {"POINTS":"PTS","REBOUNDS":"REB","ASSISTS":"AST","THREES":"3PM","3PTM":"3PM","FG3M":"3PM","PTS+REB+AST":"PRA","PTS+REB":"PR","PTS+AST":"PA","REB+AST":"RA"}.get(raw, raw)


def decimal_odds(american: Any) -> float:
    odds = f(american, 0)
    if not odds:
        return 1.91
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def actual_value_from_row(row: Dict[str, Any], stat: str) -> Optional[float]:
    stat = norm_stat(stat)
    direct = {
        "PTS": ["PTS", "points", "actual_points"],
        "REB": ["REB", "TRB", "rebounds", "actual_rebounds"],
        "AST": ["AST", "assists", "actual_assists"],
        "3PM": ["3PM", "FG3M", "threes", "actual_3pm"],
        "PRA": ["PRA", "actual_pra"],
        "PR": ["PR", "actual_pr"],
        "PA": ["PA", "actual_pa"],
        "RA": ["RA", "actual_ra"],
    }.get(stat, [stat])
    for k in direct:
        if k in row and row[k] not in [None, "", "—"]:
            return f(row[k])
    pts = f(row.get("PTS", row.get("points", 0)))
    reb = f(row.get("REB", row.get("TRB", row.get("rebounds", 0))))
    ast = f(row.get("AST", row.get("assists", 0)))
    if stat == "PRA" and (pts or reb or ast): return pts + reb + ast
    if stat == "PR" and (pts or reb): return pts + reb
    if stat == "PA" and (pts or ast): return pts + ast
    if stat == "RA" and (reb or ast): return reb + ast
    return None


def collect_actuals(target_date: str) -> Dict[str, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    candidates = []
    for root in ["data/raw", "data/history", "data/tracking"]:
        candidates += glob(os.path.join(root, f"*{target_date}*.json"))
        candidates += glob(os.path.join(root, "*.json"))
    for path in candidates:
        data = load_json(path, None)
        if data is None:
            continue
        if isinstance(data, list):
            rows.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict):
            for key in ["player_stats", "boxscores", "results", "rows", "data", "props", "bets"]:
                if isinstance(data.get(key), list):
                    rows.extend([x for x in data[key] if isinstance(x, dict)])
            for k, v in data.items():
                if isinstance(v, dict) and any(x in v for x in ["PTS", "points", "actual"]):
                    tmp = dict(v); tmp.setdefault("player", k); rows.append(tmp)
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.get("date") and target_date not in str(r.get("date")):
            continue
        name = norm_name(r.get("player") or r.get("name") or r.get("athlete") or r.get("player_name"))
        if name:
            out[name] = r
    return out


def final_action(row: Dict[str, Any]) -> str:
    if isinstance(row.get("daily_action_v2"), dict):
        return str(row["daily_action_v2"].get("final_action") or "").upper()
    return str(row.get("final_action") or row.get("timing_action") or row.get("decision") or row.get("action") or "").upper()


def grade_bet(row: Dict[str, Any], actuals: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    action = final_action(row)
    if action not in {"BET NOW", "BET SOON", "LEAN", "BET", "PLAY"}:
        return None
    player_key = norm_name(row.get("player"))
    actual = None
    if player_key in actuals:
        actual = actual_value_from_row(actuals[player_key], row.get("stat"))
    for k in ["actual", "actual_value", "result_value", "final"]:
        if actual is None and row.get(k) not in [None, "", "—"]:
            actual = f(row.get(k))
    if actual is None:
        return {"status": "PENDING", "actual": None}
    line = f(row.get("line"))
    signal = str(row.get("signal") or "").upper()
    if signal == "OVER":
        result = "WIN" if actual > line else "LOSS" if actual < line else "PUSH"
    elif signal == "UNDER":
        result = "WIN" if actual < line else "LOSS" if actual > line else "PUSH"
    else:
        result = "UNKNOWN"
    units = f(row.get("recommended_units", row.get("units", 1)), 1) or 1
    if result == "WIN":
        profit = units * (decimal_odds(row.get("odds", row.get("price", row.get("best_odds")))) - 1)
    elif result == "LOSS":
        profit = -units
    else:
        profit = 0
    pred = f(row.get("median_projection_v2", row.get("pred", row.get("projection", 0))))
    return {
        "status": result,
        "actual": round(actual, 2),
        "profit_units": round(profit, 2),
        "projection_error": round(actual - pred, 2) if pred else None,
    }


def reasons(row: Dict[str, Any], grade: Dict[str, Any]) -> List[str]:
    out = []
    if grade.get("projection_error") is not None:
        err = f(grade.get("projection_error"))
        if abs(err) <= 1.5:
            out.append("projection was close")
        elif err > 0:
            out.append("actual finished above projection")
        else:
            out.append("actual finished below projection")
    if str(row.get("rotation_risk_level", "")).upper() == "HIGH":
        out.append("rotation risk was present")
    pi = row.get("projection_intelligence_v2") or {}
    if str(pi.get("volatility", "")).upper() == "HIGH":
        out.append("high volatility projection")
    mt = row.get("market_timing_intelligence") or {}
    if f(mt.get("expected_clv", row.get("expected_clv_v2", 0))) < 0:
        out.append("negative CLV signal")
    if not out:
        out.append("standard variance / no clear failure flag")
    return out[:4]


def slim(row: Dict[str, Any], grade: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "player": row.get("player"), "team": row.get("team"), "game": row.get("game"),
        "stat": norm_stat(row.get("stat")), "signal": row.get("signal"), "line": row.get("line"),
        "odds": row.get("odds", row.get("price", row.get("best_odds"))),
        "sportsbook": row.get("best_book_title") or row.get("best_book") or row.get("sportsbook"),
        "projection": row.get("median_projection_v2", row.get("pred", row.get("projection"))),
        "actual": grade.get("actual"), "status": grade.get("status"),
        "profit_units": grade.get("profit_units"), "projection_error": grade.get("projection_error"),
        "final_action": final_action(row), "reasons": reasons(row, grade),
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    actuals = collect_actuals(target_date)
    graded = []
    for p in props:
        g = grade_bet(p, actuals)
        if g:
            graded.append((p, g))
    completed = [(p, g) for p, g in graded if g.get("status") in {"WIN", "LOSS", "PUSH"}]
    pending = [(p, g) for p, g in graded if g.get("status") == "PENDING"]
    wins = sum(1 for _, g in completed if g.get("status") == "WIN")
    losses = sum(1 for _, g in completed if g.get("status") == "LOSS")
    pushes = sum(1 for _, g in completed if g.get("status") == "PUSH")
    profit = round(sum(f(g.get("profit_units")) for _, g in completed), 2)
    by_stat = defaultdict(list)
    by_book = defaultdict(list)
    for p, g in completed:
        by_stat[norm_stat(p.get("stat"))].append(g)
        by_book[str(p.get("best_book_title") or p.get("best_book") or p.get("sportsbook") or "Unknown")].append(g)
    worst = sorted(completed, key=lambda x: abs(f(x[1].get("projection_error"))), reverse=True)[:10]
    best = sorted([x for x in completed if x[1].get("status") == "WIN"], key=lambda x: abs(f(x[1].get("projection_error"))))[:10]
    lessons = []
    if completed:
        hit = wins / max(1, wins + losses)
        lessons.append("Positive review day" if profit > 0 else "Negative review day; reduce trust in weak signals")
        if hit < 0.5: lessons.append("Hit rate below 50%; review confidence and timing filters")
        if worst: lessons.extend([f"Big miss factor: {r}" for r in reasons(worst[0][0], worst[0][1])[:2]])
    else:
        lessons.append("No completed results found yet; review will populate after box scores are available")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "recommended_bets": len(graded), "completed_bets": len(completed), "pending_bets": len(pending),
            "wins": wins, "losses": losses, "pushes": pushes,
            "hit_rate": round(wins / max(1, wins + losses) * 100, 1) if (wins + losses) else None,
            "profit_units": profit,
            "actual_rows_found": len(actuals),
        },
        "lessons": lessons[:8],
        "wins": [slim(p, g) for p, g in completed if g.get("status") == "WIN"][:20],
        "losses": [slim(p, g) for p, g in completed if g.get("status") == "LOSS"][:20],
        "pending": [slim(p, g) for p, g in pending[:20]],
        "biggest_misses": [slim(p, g) for p, g in worst],
        "best_calls": [slim(p, g) for p, g in best],
        "stat_summary": [{"stat": k, "bets": len(v), "profit_units": round(sum(f(g.get("profit_units")) for g in v), 2)} for k, v in by_stat.items()],
        "sportsbook_summary": [{"sportsbook": k, "bets": len(v), "profit_units": round(sum(f(g.get("profit_units")) for g in v), 2)} for k, v in by_book.items()],
    }
    data["results_review_center"] = report
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    default_date = str(date.today() - timedelta(days=1))
    ap.add_argument("--date", default=default_date)
    args = ap.parse_args()
    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    data = load_json(path, {})
    report = build(data, args.date)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    os.makedirs(OUT_DASH, exist_ok=True)
    os.makedirs(OUT_INTEL, exist_ok=True)
    with open(os.path.join(OUT_DASH, "results_review_center.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_INTEL, f"results_review_center_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ Results Review Center built: {report['summary']['completed_bets']} completed bets")


if __name__ == "__main__":
    main()
