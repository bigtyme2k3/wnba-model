"""
wnba_historical_database.py
---------------------------
Appends each slate's model outputs to a persistent historical database.

Outputs:
- data/history/wnba_model_history.jsonl
- data/warehouse/wnba_historical_summary.json
- data/dashboard/wnba_historical_summary.json
"""
from __future__ import annotations

import argparse, json, os
from datetime import date, datetime, timezone
from typing import Any, Dict, List

HISTORY_PATH = "data/history/wnba_model_history.jsonl"


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception:
        pass
    return default


def append_unique(records: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    seen = set()
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    r=json.loads(line); seen.add(r.get("history_key"))
                except Exception: pass
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        for r in records:
            if r.get("history_key") not in seen:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
                seen.add(r.get("history_key"))


def read_history() -> List[Dict[str, Any]]:
    rows=[]
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except Exception: pass
    return rows


def build(target: str) -> Dict[str, Any]:
    consensus = load_json("data/warehouse/wnba_consensus_engine.json", {})
    points = load_json(f"predictions/predictions_{target}.json", {})
    now = datetime.now(timezone.utc).isoformat()
    records=[]
    for r in consensus.get("all_consensus", []) if isinstance(consensus, dict) else []:
        hk = f"{target}|{r.get('player')}|{r.get('game')}|{r.get('stat')}|{r.get('line')}|{r.get('signal')}"
        records.append({
            "history_key": hk,
            "date": target,
            "captured_at_utc": now,
            "player": r.get("player"),
            "team": r.get("team"),
            "game": r.get("game"),
            "stat": r.get("stat"),
            "line": r.get("line"),
            "pred": r.get("pred"),
            "signal": r.get("signal"),
            "edge": r.get("edge"),
            "ev_pct": r.get("ev_pct"),
            "consensus_score": r.get("consensus_score"),
            "consensus_grade": r.get("consensus_grade"),
            "engine_agreement": r.get("engine_agreement"),
            "recommendation": r.get("recommendation"),
            "outcome": None,
            "actual": None,
            "clv": None,
        })
    append_unique(records)
    hist = read_history()
    by_rec={}
    for r in hist:
        rec=r.get("recommendation","UNKNOWN")
        by_rec[rec]=by_rec.get(rec,0)+1
    summary={
        "generated_at_utc": now,
        "target_date": target,
        "added_records": len(records),
        "total_records": len(hist),
        "by_recommendation": by_rec,
        "recent_records": hist[-50:],
        "source_predictions_games": len(points.get("games", [])) if isinstance(points, dict) else 0,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_historical_summary.json", "data/dashboard/wnba_historical_summary.json"]:
        with open(path,"w",encoding="utf-8") as f: json.dump(summary,f,indent=2)
    return summary


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date", default=str(date.today())); args=ap.parse_args()
    print(f"✅ Historical database updated: {build(args.date)}")

if __name__ == "__main__": main()
