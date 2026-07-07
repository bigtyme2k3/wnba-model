"""
wnba_self_learning.py
---------------------
Creates adaptive engine weights from historical records.

At first this is conservative because outcomes may be sparse. As actual results,
CLV, and grading data accumulate, these weights become more useful.

Outputs:
- data/warehouse/wnba_self_learning.json
- data/dashboard/wnba_self_learning.json
"""
from __future__ import annotations

import argparse, json, os
from datetime import date, datetime, timezone
from typing import Any, Dict, List

HISTORY_PATH="data/history/wnba_model_history.jsonl"
ENGINES=["Projection EV","Projection Edge","Player Intelligence","Matchup Intelligence","Injury Engine","Market Engine","DeepSeek Engine"]


def read_history() -> List[Dict[str, Any]]:
    rows=[]
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except Exception: pass
    return rows


def build(target: str) -> Dict[str, Any]:
    hist=read_history()
    graded=[r for r in hist if r.get("outcome") in {"WIN","LOSS","PUSH"}]
    weights={e: round(1/len(ENGINES),4) for e in ENGINES}
    notes=[]
    if len(graded) < 25:
        notes.append("Not enough graded results yet; using balanced starter weights.")
    else:
        # Starter learning rule until full engine-level attribution is available.
        wins=sum(1 for r in graded if r.get("outcome")=="WIN")
        win_rate=wins/max(1, sum(1 for r in graded if r.get("outcome") in {"WIN","LOSS"}))
        if win_rate >= 0.55:
            weights["Projection EV"] += 0.03; weights["Market Engine"] += 0.02
        else:
            weights["Player Intelligence"] += 0.025; weights["Matchup Intelligence"] += 0.025
        s=sum(weights.values()); weights={k:round(v/s,4) for k,v in weights.items()}
        notes.append(f"Applied conservative learning adjustment from {len(graded)} graded records.")
    report={
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "history_records": len(hist),
        "graded_records": len(graded),
        "engine_weights": weights,
        "notes": notes,
        "next_learning_needs": ["actual stat results", "closing lines", "engine-level vote outcome attribution"]
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_self_learning.json", "data/dashboard/wnba_self_learning.json"]:
        with open(path,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
    return report


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date", default=str(date.today())); args=ap.parse_args()
    print(f"✅ Self-learning engine built: {build(args.date)}")

if __name__=="__main__": main()
