"""Validation Week Commit 1: persist live WNBA market predictions for later grading.

Each run captures one current record per actionable market from the live scanner and
stores it in an append-only JSON ledger. Records are deduplicated by market ID and
capture timestamp. This tracker records model state; it does not claim a wager occurred.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIVE = Path("data/forecast/live_opportunity_scanner.json")
PRED = Path("data/forecast/closing_line_predictions.json")
TIMELINE = Path("data/market/market_timeline.json")
OUT = Path("data/validation/live_prediction_tracker.json")
DASH = Path("data/dashboard/wnba_live_prediction_tracker_summary.json")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def latest_observation_map() -> dict[str, dict[str, Any]]:
    rows = load(TIMELINE).get("markets", [])
    output: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        obs = row.get("observations") or []
        if obs:
            output[str(row.get("market_id"))] = obs[-1]
    return output


def run() -> dict[str, Any]:
    captured = now()
    live_payload = load(LIVE)
    markets = live_payload.get("markets", [])
    markets = markets if isinstance(markets, list) else []
    prediction_rows = load(PRED).get("predictions", []) or load(PRED).get("forecasts", [])
    pred_map = {str(x.get("market_id")): x for x in prediction_rows if isinstance(x, dict) and x.get("market_id")}
    obs_map = latest_observation_map()

    prior = load(OUT)
    records = prior.get("records", [])
    records = records if isinstance(records, list) else []
    seen = {(str(x.get("market_id")), str(x.get("captured_at_utc"))) for x in records if isinstance(x, dict)}

    added = []
    for row in markets:
        mid = str(row.get("market_id") or "")
        if not mid or (mid, captured) in seen:
            continue
        p = pred_map.get(mid, {})
        latest = obs_map.get(mid, {})
        rec = {
            "capture_id": f"{captured}|{mid}",
            "captured_at_utc": captured,
            "market_id": mid,
            "event_id": row.get("event_id"),
            "commence_time_utc": row.get("commence_time_utc"),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "bookmaker": row.get("bookmaker"),
            "market": row.get("market"),
            "participant": row.get("participant"),
            "selection": row.get("selection"),
            "opening_line": row.get("opening_line"),
            "current_line": row.get("current_point"),
            "current_price": row.get("current_price"),
            "snapshot_time_utc": row.get("last_update_utc") or latest.get("snapshot_time_utc"),
            "projected_closing_line": row.get("projected_closing_point") or p.get("projected_closing_point"),
            "projected_closing_price": row.get("projected_closing_price") or p.get("projected_closing_price"),
            "prediction_interval": p.get("projected_point_interval"),
            "forecast_status": row.get("forecast_status") or p.get("forecast_status"),
            "forecast_confidence": row.get("forecast_confidence") or p.get("forecast_confidence"),
            "scanner_recommendation": row.get("scanner_recommendation"),
            "opportunity_score": row.get("live_opportunity_score") or row.get("opportunity_score"),
            "tier": row.get("tier"),
            "entry_action": row.get("entry_action"),
            "signal": row.get("signal"),
            "volatility_score": row.get("volatility_score"),
            "freshness_score": row.get("freshness_score"),
            "matched_clv_trends": row.get("matched_clv_trends", 0),
            "matched_validated_trends": row.get("matched_validated_trends", 0),
            "actual_closing_line": None,
            "actual_closing_price": None,
            "final_home_score": None,
            "final_away_score": None,
            "grade": None,
            "profit_units": None,
            "validation_status": "OPEN",
            "tracking_note": "Model-state capture only; no executed wager is implied.",
        }
        records.append(rec)
        added.append(rec)

    records.sort(key=lambda x: (str(x.get("captured_at_utc")), str(x.get("market_id"))))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    DASH.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at_utc": captured,
        "methodology": "Append-only captures of live scanner and closing-line forecast state for later closing-line and outcome validation.",
        "records": records,
    }, indent=2), encoding="utf-8")

    open_records = sum(x.get("validation_status") == "OPEN" for x in records)
    summary = {
        "generated_at_utc": captured,
        "status": "READY" if added else ("STANDBY" if not markets else "NO_CHANGE"),
        "live_markets_seen": len(markets),
        "records_added": len(added),
        "records_total": len(records),
        "open_records": open_records,
        "events_captured": len({x.get("event_id") for x in added if x.get("event_id")}),
        "recommendation_counts_added": {k: sum(x.get("scanner_recommendation") == k for x in added) for k in ["BET_NOW", "WATCH", "PASS"]},
        "top_captures": sorted(added, key=lambda x: -float(x.get("opportunity_score") or 0))[:25],
        "warning": "Tracking records preserve model state for research validation and do not represent placed wagers.",
    }
    DASH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
