"""Persist each slate's quality-controlled model decisions for grading and learning."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List

HISTORY_PATH = "data/history/wnba_model_history.jsonl"


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    except Exception:
        pass
    return default


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def read_history() -> List[Dict[str, Any]]:
    rows = []
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except Exception:
                    pass
    return rows


def append_unique(records: List[Dict[str, Any]]) -> int:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    existing = read_history()
    seen = {row.get("history_key") for row in existing}
    added = 0
    with open(HISTORY_PATH, "a", encoding="utf-8") as handle:
        for record in records:
            if record.get("history_key") in seen:
                continue
            handle.write(json.dumps(clean(record), separators=(",", ":"), allow_nan=False) + "\n")
            seen.add(record.get("history_key"))
            added += 1
    return added


def source_rows() -> List[Dict[str, Any]]:
    decisions = load_json("data/warehouse/wnba_decision_engine_final.json", {})
    rows = decisions.get("top_decisions", []) if isinstance(decisions, dict) else []
    if rows:
        return rows
    consensus = load_json("data/warehouse/wnba_consensus_engine.json", {})
    return consensus.get("all_consensus", []) if isinstance(consensus, dict) else []


def build(target: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for row in source_rows():
        action = row.get("final_action") or row.get("recommendation") or "UNRANKED"
        history_key = f"{target}|{row.get('player')}|{row.get('game')}|{row.get('stat')}|{row.get('line')}|{row.get('signal')}"
        records.append({
            "history_key": history_key,
            "date": target,
            "captured_at_utc": now,
            "player": row.get("player"),
            "team": row.get("team"),
            "game": row.get("game"),
            "stat": row.get("stat"),
            "line": row.get("line"),
            "pred": row.get("pred"),
            "signal": row.get("signal"),
            "edge": row.get("edge"),
            "edge_pct": row.get("edge_pct"),
            "raw_ev_pct": row.get("raw_ev_pct"),
            "ev_pct": row.get("ev_pct"),
            "consensus_score": row.get("consensus_score"),
            "confidence": row.get("confidence", row.get("final_score")),
            "final_score": row.get("final_score"),
            "simulation_probability": row.get("simulation_probability"),
            "engine_agreement": row.get("engine_agreement"),
            "recommendation": action,
            "final_action": action,
            "eligible_for_bet": row.get("eligible_for_bet", False),
            "sportsbook": row.get("sportsbook"),
            "american_odds": row.get("american_odds"),
            "book_count": row.get("book_count"),
            "history_games": row.get("history_games"),
            "decision_reason": row.get("decision_reason"),
            "guardrail_failures": row.get("guardrail_failures", []),
            "outcome": None,
            "actual": None,
            "closing_line": None,
            "clv": None,
        })

    added = append_unique(records)
    history = read_history()
    by_action: Dict[str, int] = {}
    for row in history:
        action = str(row.get("final_action") or row.get("recommendation") or "UNKNOWN")
        by_action[action] = by_action.get(action, 0) + 1
    summary = {
        "generated_at_utc": now,
        "target_date": target,
        "candidate_records": len(records),
        "added_records": added,
        "total_records": len(history),
        "by_action": by_action,
        "graded_records": sum(row.get("outcome") in {"WIN", "LOSS", "PUSH"} for row in history),
        "recent_records": history[-50:],
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_historical_summary.json", "data/dashboard/wnba_historical_summary.json"]:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(clean(summary), handle, indent=2, allow_nan=False)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    print("Historical database updated:", build(args.date))


if __name__ == "__main__":
    main()
