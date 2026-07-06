"""
dashboard_health.py
-------------------
Builds a lightweight dashboard health center and daily AI briefing.

This script does not call external APIs. It only inspects files already created
by the daily pipeline and patches predictions/predictions_YYYY-MM-DD.json with:
  - dashboard_health
  - daily_briefing

The UI patch reads those fields directly from the baked DATA object.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone

import pandas as pd

RAW_DIR = "data/raw"
PRED_DIR = "predictions"
STRATEGY_DIR = "data/strategies"
TRACKING_DIR = "data/tracking"


def load_csv(path):
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def load_json(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def file_age_minutes(path):
    if not path or not os.path.exists(path):
        return None
    mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    return round((datetime.now(timezone.utc) - mtime).total_seconds() / 60, 1)


def status_from_rows(rows, required=True):
    if rows > 0:
        return "ok"
    return "warn" if required else "idle"


def source_health(name, path, rows=0, required=True, note=""):
    age = file_age_minutes(path) if path else None
    return {
        "name": name,
        "status": status_from_rows(rows, required),
        "rows": int(rows or 0),
        "file": path or "",
        "age_minutes": age,
        "note": note or ("loaded" if rows else "missing or empty"),
    }


def build_health(target_date, data):
    odds_path = first_existing([os.path.join(RAW_DIR, f"odds_{target_date}.csv"), os.path.join(RAW_DIR, "odds_today.csv")])
    props_path = first_existing([os.path.join(RAW_DIR, f"props_raw_{target_date}.csv"), os.path.join(RAW_DIR, "props_today.csv")])
    injuries_path = first_existing([os.path.join(RAW_DIR, f"injuries_{target_date}.csv"), os.path.join(RAW_DIR, "injuries_today.csv")])
    player_stats_path = os.path.join(RAW_DIR, "wnba_players_live.json")
    strategy_path = os.path.join(STRATEGY_DIR, "live_strategy_recommendations.json")
    model_tracking_path = os.path.join(TRACKING_DIR, "model_tracking.json")

    odds = load_csv(odds_path)
    props = load_csv(props_path)
    injuries = load_csv(injuries_path)
    player_stats = load_json(player_stats_path) or {}
    strategies = load_json(strategy_path) or {}
    model_tracking = load_json(model_tracking_path) or {}

    health = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "overall_status": "ok",
        "sources": [
            source_health("Odds Feed", odds_path, len(odds), True, "spreads, totals, moneylines"),
            source_health("Props Feed", props_path, len(props), False, "player prop markets"),
            source_health("Injury Feed", injuries_path, len(injuries), False, "availability and injury status"),
            source_health("Player Stats", player_stats_path if os.path.exists(player_stats_path) else None, len(player_stats), False, "official WNBA player stats"),
            source_health("Strategy Lab", strategy_path if os.path.exists(strategy_path) else None, len(strategies.get("recommendations", strategies.get("strategies", []))) if isinstance(strategies, dict) else 0, False, "historical strategy matches"),
            source_health("Model Tracking", model_tracking_path if os.path.exists(model_tracking_path) else None, int(model_tracking.get("bets", 0)) if isinstance(model_tracking, dict) else 0, False, "tracking and calibration"),
        ],
        "counts": {
            "games": len(data.get("games", []) or []),
            "props": len(data.get("props", []) or []),
            "best_bets": len(data.get("best_bets", []) or []),
            "slips": len((data.get("slip_optimizer", {}) or {}).get("slips", []) or []),
            "alerts": len(data.get("live_alerts", []) or []),
            "correlations": len(data.get("correlations", []) or []),
        },
        "api_usage": {
            "provider": "The Odds API",
            "status": "manual_check_required",
            "note": "Credits are not exposed to GitHub Actions unless added separately. Use this panel as a feed-health check.",
        },
    }

    if any(s["status"] == "warn" for s in health["sources"][:1]):
        health["overall_status"] = "warn"
    elif any(s["status"] == "warn" for s in health["sources"]):
        health["overall_status"] = "partial"
    return health


def pick_top(items, key, n=1):
    return sorted(items, key=lambda x: float(x.get(key, 0) or 0), reverse=True)[:n]


def build_briefing(data, health):
    props = data.get("props", []) or []
    best_bets = data.get("best_bets", []) or []
    slips = (data.get("slip_optimizer", {}) or {}).get("slips", []) or []
    correlations = data.get("correlations", []) or []

    elite = [b for b in best_bets if str(b.get("score_label", b.get("grade", ""))).upper() in {"ELITE", "A+"} or float(b.get("score", 0) or 0) >= 92]
    high = [b for b in best_bets if float(b.get("score", 0) or 0) >= 84]
    high_props = [p for p in props if float(p.get("confidence_v2", p.get("score", 0)) or 0) >= 84]
    top_ev = pick_top(best_bets or props, "ev_pct", 1)
    top_conf = pick_top(high_props or props, "confidence_v2", 1)
    top_corr = sorted(correlations, key=lambda c: abs(float(c.get("correlation", 0) or 0)), reverse=True)[:1]
    best_slip = sorted(slips, key=lambda s: float(s.get("ev_pct", 0) or 0), reverse=True)[:1]

    bullets = []
    bullets.append(f"{health['counts'].get('games', 0)} games loaded with {health['counts'].get('props', 0)} prop markets.")
    bullets.append(f"{len(elite)} elite bets and {len(high)} strong bets found." if best_bets else "No best bets generated yet.")
    if top_ev:
        b = top_ev[0]
        bullets.append(f"Highest EV: {b.get('play') or b.get('player') or 'market'} at {b.get('ev_pct', '—')}% EV.")
    if top_conf:
        p = top_conf[0]
        bullets.append(f"Top confidence prop: {p.get('player', 'Player')} {p.get('stat', '')} {p.get('signal', '')} ({p.get('confidence_v2', p.get('score', '—'))}/100).")
    if best_slip:
        s = best_slip[0]
        bullets.append(f"Best slip: {s.get('label', 'Optimized slip')} at {s.get('ev_pct', '—')}% EV and {s.get('model_prob_pct', '—')}% model probability.")
    if top_corr:
        c = top_corr[0]
        bullets.append(f"Correlation watch: {c.get('a')} / {c.get('b')} ({c.get('correlation')}).")
    if health.get("overall_status") != "ok":
        bullets.append("One or more feeds are partial. Check Dashboard Health before trusting stale markets.")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "headline": "Daily AI Brief",
        "summary": "Today's slate, model health, and highest-value opportunities in one view.",
        "bullets": bullets[:8],
        "top_ev": top_ev[:3],
        "top_confidence": top_conf[:3],
        "best_slips": best_slip[:2],
        "health_status": health.get("overall_status", "ok"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()

    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    with open(path, "r") as f:
        data = json.load(f)

    health = build_health(args.date, data)
    briefing = build_briefing(data, health)
    data["dashboard_health"] = health
    data["daily_briefing"] = briefing

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    os.makedirs("data/intelligence", exist_ok=True)
    with open(f"data/intelligence/dashboard_health_{args.date}.json", "w") as f:
        json.dump(health, f, indent=2)
    with open(f"data/intelligence/daily_briefing_{args.date}.json", "w") as f:
        json.dump(briefing, f, indent=2)

    print(f"✅ Dashboard health + briefing added to {path}")
    print(f"   Status: {health['overall_status']} | Props: {health['counts']['props']} | Best bets: {health['counts']['best_bets']}")


if __name__ == "__main__":
    main()
