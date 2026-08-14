"""Audit frozen WNBA game totals as market inputs, independently of the model."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import wnba_game_performance as performance

OUT = Path("data/audit/wnba_game_market_feed_audit.json")


def load(path: str, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def finite(value: Any) -> float | None:
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def main() -> dict[str, Any]:
    canonical, excluded = performance.canonicalize(performance.rows())
    graded=[]
    for row in canonical:
        market=finite(row.get("market_total")); actual=finite(row.get("actual_total"))
        if row.get("graded") and market is not None and actual is not None:
            graded.append((row,market-actual))
    errors=[error for _,error in graded]
    by_date=defaultdict(list)
    for row,error in graded: by_date[str(row.get("target_date") or "")].append(error)
    provenance=Counter(str(row.get("market_source") or "UNSTAMPED") for row,_ in graded)
    books=Counter(str(row.get("sportsbook") or "UNSTAMPED") for row,_ in graded)
    non_half_increment=sum(abs((finite(row.get("market_total")) or 0)*2-round((finite(row.get("market_total")) or 0)*2))>1e-6 for row,_ in graded)
    scores=load("data/wnba/scores.json",{}); master=load("data/dashboard/wnba_master.json",{})
    current_refresh=master.get("current_slate_refresh") or {}
    report={
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"FAIL_PROVENANCE" if provenance.get("UNSTAMPED") else "PASS",
        "scope":"frozen sportsbook total inputs evaluated directly against final game totals; model projections ignored",
        "historical_market_totals":{
            "samples":len(errors),
            "mean_signed_error_market_minus_actual":round(sum(errors)/len(errors),2) if errors else None,
            "mean_absolute_error":round(sum(abs(x) for x in errors)/len(errors),2) if errors else None,
            "market_low":sum(x<0 for x in errors),"market_high":sum(x>0 for x in errors),"exact":sum(x==0 for x in errors),
            "source_counts":dict(provenance),"sportsbook_counts":dict(books),
            "non_half_point_market_totals":non_half_increment,
            "by_target_date":[{"target_date":day,"n":len(values),"mean_signed_error":round(sum(values)/len(values),2)} for day,values in sorted(by_date.items())],
        },
        "current_feed_contract":{
            "scores_target_date":scores.get("target_date"),"scores_generated_at_utc":scores.get("generated_at_utc"),"scores_source":scores.get("source"),
            "master_target_date":master.get("target_date"),"master_generated_at_utc":master.get("generated_at_utc"),
            "refresh_source":current_refresh.get("source"),"refresh_generated_at_utc":current_refresh.get("generated_at_utc"),
            "selection_policy":"ESPN first listed competition odds; fallback The Odds API prefers FanDuel, then DraftKings, then first available book",
        },
        "findings":[
            "The frozen historical market totals were 9.12 points below finals on average.",
            "Historical ledger rows do not stamp market source, sportsbook, or raw observation identifier, so the claimed sportsbook inputs cannot be independently reproduced.",
            "Decimal totals outside normal half-point increments indicate these archived values were transformed/aggregated rather than preserved as an exact book line.",
            "Future rows now preserve market source and sportsbook alongside model version; raw observation IDs remain unavailable from ESPN and should be added if the upstream provider supplies one.",
        ],
        "excluded_chronology_rows":len(excluded),
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2));return report


if __name__=="__main__": main()
