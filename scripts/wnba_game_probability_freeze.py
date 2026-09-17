"""Freeze honest pregame spread/total probabilities onto pending game predictions.

This module is prospective-only. It never backfills graded predictions. Probabilities
are derived from the current model edge and residual dispersion observed only in
previously graded predictions whose target_date is before the pending prediction.
That prevents outcome leakage while allowing the Game Performance calibration
panel to begin accumulating real Brier/ECE evidence.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from typing import Any

LEDGER = Path("data/history/wnba_game_predictions.jsonl")
MIN_HISTORY = 20
MIN_SIGMA = 3.0


def num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def read_rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows=[]
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict): rows.append(row)
        except Exception:
            pass
    return rows


def write_rows(rows: list[dict[str, Any]]) -> None:
    with LEDGER.open("w",encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")


def prior_residuals(rows: list[dict[str, Any]], target: str, projected: str, actual: str) -> list[float]:
    out=[]
    for row in rows:
        if not row.get("graded") or str(row.get("target_date") or "")[:10] >= target:
            continue
        p=num(row.get(projected)); a=num(row.get(actual))
        if p is not None and a is not None:
            out.append(a-p)
    return out


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--date",required=True); args=ap.parse_args()
    target=args.date
    rows=read_rows()
    spread_res=prior_residuals(rows,target,"projected_margin","actual_margin")
    total_res=prior_residuals(rows,target,"projected_total","actual_total")
    spread_sigma=max(MIN_SIGMA,pstdev(spread_res)) if len(spread_res)>=MIN_HISTORY else None
    total_sigma=max(MIN_SIGMA,pstdev(total_res)) if len(total_res)>=MIN_HISTORY else None
    changed=0
    for row in rows:
        if str(row.get("target_date") or "")[:10] != target or row.get("graded"):
            continue
        # Never overwrite a probability already frozen by the producer.
        spread_edge=num(row.get("spread_edge")); total_edge=num(row.get("total_edge"))
        if row.get("spread_probability") is None and spread_sigma is not None and spread_edge is not None:
            # Probability is for the frozen spread_pick direction.
            row["spread_probability"]=round(normal_cdf(abs(spread_edge)/spread_sigma),4)
            changed+=1
        if row.get("total_probability") is None and total_sigma is not None and total_edge is not None:
            # Probability is for the frozen OVER/UNDER total_pick direction.
            row["total_probability"]=round(normal_cdf(abs(total_edge)/total_sigma),4)
            changed+=1
        if row.get("spread_probability") is not None or row.get("total_probability") is not None:
            row["probability_method"]="prospective_empirical_residual_normal_v1"
            row["probability_history_cutoff"] = target
            row["probability_history_games"]={"spread":len(spread_res),"total":len(total_res)}
            row["probability_sigma"]={"spread":round(spread_sigma,4) if spread_sigma is not None else None,"total":round(total_sigma,4) if total_sigma is not None else None}
            row["probability_frozen_at_utc"]=datetime.now(timezone.utc).isoformat()
    write_rows(rows)
    print(json.dumps({"status":"PASS","target_date":target,"changed_fields":changed,"spread_history":len(spread_res),"total_history":len(total_res),"spread_sigma":spread_sigma,"total_sigma":total_sigma,"retroactive_backfill":False}))

if __name__=="__main__": main()
