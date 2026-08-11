"""Build game-level performance analytics from the frozen prediction ledger.

Only chronology-verifiable pregame snapshots are eligible for performance
metrics. Rows without a usable start time, rows captured after tipoff, and
superseded duplicate snapshots remain in the raw ledger for auditability but do
not influence model evaluation.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path("data/history/wnba_game_predictions.jsonl")
OUTPUTS = [Path("data/dashboard/wnba_game_performance.json"), Path("data/warehouse/wnba_game_performance.json")]


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def parse_time(value: Any) -> datetime | None:
    try:
        text = str(value or "").strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            except Exception:
                pass
    return out


def canonicalize(data: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return chronology-safe pregame snapshots and excluded audit rows."""
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in data:
        captured = parse_time(row.get("captured_at_utc"))
        start = parse_time(row.get("start_time"))
        if start is None:
            excluded.append({"prediction_id": row.get("prediction_id"), "target_date": row.get("target_date"), "game": row.get("game"), "reason": "missing_start_time"})
            continue
        if captured is None:
            excluded.append({"prediction_id": row.get("prediction_id"), "target_date": row.get("target_date"), "game": row.get("game"), "reason": "missing_capture_time"})
            continue
        if captured >= start:
            excluded.append({"prediction_id": row.get("prediction_id"), "target_date": row.get("target_date"), "game": row.get("game"), "reason": "captured_at_or_after_tipoff"})
            continue
        eligible.append(row)

    # Same matchup/start time can appear under more than one stale slate date.
    # Preserve only the latest genuinely pregame snapshot for that event.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        groups[(norm(row.get("game")), str(row.get("start_time") or ""))].append(row)
    canonical: list[dict[str, Any]] = []
    for group in groups.values():
        group.sort(key=lambda r: parse_time(r.get("captured_at_utc")) or datetime.min.replace(tzinfo=timezone.utc))
        keep = group[-1]
        canonical.append(keep)
        for row in group[:-1]:
            excluded.append({"prediction_id": row.get("prediction_id"), "target_date": row.get("target_date"), "game": row.get("game"), "reason": "superseded_pregame_snapshot"})
    return canonical, excluded


def rate(wins: int, losses: int) -> float | None:
    decisions = wins + losses
    return round(wins / decisions, 4) if decisions else None


def market_summary(data: list[dict[str, Any]], result_key: str, rec_key: str) -> dict[str, Any]:
    graded = [r for r in data if r.get("graded") and r.get(result_key) not in {None, "PASS", "VOID"}]
    wins = sum(r.get(result_key) == "WIN" for r in graded)
    losses = sum(r.get(result_key) == "LOSS" for r in graded)
    pushes = sum(r.get(result_key) == "PUSH" for r in graded)
    sides: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "pushes": 0})
    for row in graded:
        side = str(row.get(rec_key) or "UNKNOWN")
        result = str(row.get(result_key))
        if result == "WIN": sides[side]["wins"] += 1
        elif result == "LOSS": sides[side]["losses"] += 1
        elif result == "PUSH": sides[side]["pushes"] += 1
    return {"record": {"wins": wins, "losses": losses, "pushes": pushes}, "hit_rate": rate(wins, losses), "by_side": [{"side": key, **value, "hit_rate": rate(value["wins"], value["losses"])} for key, value in sorted(sides.items())]}


def spread_pick_outcome(row: dict[str, Any]) -> str | None:
    pick = str(row.get("spread_pick") or "").strip()
    spread = num(row.get("market_spread")); away = num(row.get("actual_away_score")); home = num(row.get("actual_home_score"))
    if not pick or pick.upper() == "PASS" or spread is None or away is None or home is None: return None
    home_cover = (home + spread) - away
    if abs(home_cover) < 1e-9: return "PUSH"
    picked_home = norm(pick) == norm(row.get("home_team"))
    return "WIN" if (home_cover > 0) == picked_home else "LOSS"


def total_pick_outcome(row: dict[str, Any]) -> str | None:
    pick = str(row.get("total_pick") or "").upper().strip(); line = num(row.get("market_total")); actual = num(row.get("actual_total"))
    if pick not in {"OVER", "UNDER"} or line is None or actual is None: return None
    if abs(actual - line) < 1e-9: return "PUSH"
    return "WIN" if (pick == "OVER" and actual > line) or (pick == "UNDER" and actual < line) else "LOSS"


def calibration(data: list[dict[str, Any]], probability_key: str, outcome_fn) -> dict[str, Any]:
    observations: list[tuple[float, int]] = []
    for row in data:
        if not row.get("graded"): continue
        probability = num(row.get(probability_key)); outcome = outcome_fn(row)
        if probability is None or outcome not in {"WIN", "LOSS"}: continue
        observations.append((max(0.0, min(1.0, probability)), 1 if outcome == "WIN" else 0))
    brier = round(sum((p-y)**2 for p,y in observations)/len(observations), 4) if observations else None
    buckets = []
    for low, high in ((0.50,0.55),(0.55,0.60),(0.60,0.65),(0.65,0.70),(0.70,0.80),(0.80,1.01)):
        values=[(p,y) for p,y in observations if low <= p < high]
        if not values: continue
        avg=sum(p for p,_ in values)/len(values); hit=sum(y for _,y in values)/len(values)
        buckets.append({"label":f"{int(low*100)}-{int(min(high,1.0)*100)}%","samples":len(values),"avg_probability":round(avg,4),"hit_rate":round(hit,4),"calibration_gap":round(hit-avg,4)})
    return {"samples":len(observations),"brier_score":brier,"buckets":buckets}


def edge_buckets(data: list[dict[str, Any]], edge_key: str, outcome_fn) -> list[dict[str, Any]]:
    out=[]
    for low,high in ((0,2.5),(2.5,5),(5,8),(8,12),(12,float("inf"))):
        decisions=[]
        for row in data:
            if not row.get("graded"): continue
            edge=num(row.get(edge_key)); result=outcome_fn(row)
            if edge is None or result not in {"WIN","LOSS","PUSH"}: continue
            if low <= abs(edge) < high: decisions.append(result)
        if decisions:
            wins=decisions.count("WIN"); losses=decisions.count("LOSS"); pushes=decisions.count("PUSH")
            out.append({"label":f"{low:g}-{high:g}" if math.isfinite(high) else f"{low:g}+","samples":len(decisions),"wins":wins,"losses":losses,"pushes":pushes,"hit_rate":rate(wins,losses)})
    return out


def mean(values: list[float]) -> float | None:
    return round(sum(values)/len(values),2) if values else None


def build() -> dict[str, Any]:
    raw = rows(); data, excluded = canonicalize(raw); graded=[r for r in data if r.get("graded")]
    margin_abs=[]; total_abs=[]; margin_signed=[]; total_signed=[]; away_score_abs=[]; home_score_abs=[]; winner_correct=0; winner_decisions=0; enriched=[]
    for row in graded:
        item=dict(row)
        pm=num(row.get("projected_margin")); am=num(row.get("actual_margin")); pt=num(row.get("projected_total")); at=num(row.get("actual_total")); pa=num(row.get("projected_away_score")); ph=num(row.get("projected_home_score")); aa=num(row.get("actual_away_score")); ah=num(row.get("actual_home_score"))
        if pm is not None and am is not None:
            signed=pm-am; margin_signed.append(signed); margin_abs.append(abs(signed)); item["margin_bias"]=round(signed,2)
        if pt is not None and at is not None:
            signed=pt-at; total_signed.append(signed); total_abs.append(abs(signed)); item["total_bias"]=round(signed,2)
        if pa is not None and aa is not None: away_score_abs.append(abs(pa-aa))
        if ph is not None and ah is not None: home_score_abs.append(abs(ph-ah))
        predicted_winner=row.get("home_team") if pm is not None and pm>0 else row.get("away_team") if pm is not None and pm<0 else None
        actual_winner=row.get("home_team") if am is not None and am>0 else row.get("away_team") if am is not None and am<0 else None
        if predicted_winner and actual_winner:
            winner_decisions+=1; correct=norm(predicted_winner)==norm(actual_winner); winner_correct+=int(correct); item.update({"predicted_winner":predicted_winner,"actual_winner":actual_winner,"winner_result":"WIN" if correct else "LOSS"})
        item["spread_pick_result"]=spread_pick_outcome(row); item["total_pick_result"]=total_pick_outcome(row); enriched.append(item)
    spread=market_summary(data,"spread_result","spread_recommendation"); total=market_summary(data,"total_result","total_recommendation")
    over_games=under_games=0
    for row in graded:
        actual=num(row.get("actual_total")); market=num(row.get("market_total"))
        if actual is None or market is None: continue
        over_games += actual>market; under_games += actual<market
    excluded_counts=defaultdict(int)
    for row in excluded: excluded_counts[row["reason"]]+=1
    report={
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),"status":"ok",
        "summary":{
            "raw_ledger_rows":len(raw),"archived_games":len(data),"graded_games":len(graded),"pending_games":sum(not r.get("graded") for r in data),"grade_coverage":round(len(graded)/len(data),4) if data else None,
            "excluded_rows":len(excluded),"excluded_by_reason":dict(sorted(excluded_counts.items())),
            "winner_accuracy":round(winner_correct/winner_decisions,4) if winner_decisions else None,"winner_correct":winner_correct,"winner_decisions":winner_decisions,
            "avg_margin_error":mean(margin_abs),"avg_total_error":mean(total_abs),"margin_bias":mean(margin_signed),"total_bias":mean(total_signed),"away_score_mae":mean(away_score_abs),"home_score_mae":mean(home_score_abs),"market_totals_over":over_games,"market_totals_under":under_games,
        },
        "spread":{**spread,"calibration":calibration(data,"spread_probability",spread_pick_outcome),"edge_buckets":edge_buckets(data,"spread_edge",spread_pick_outcome)},
        "total":{**total,"calibration":calibration(data,"total_probability",total_pick_outcome),"edge_buckets":edge_buckets(data,"total_edge",total_pick_outcome)},
        "recent_games":sorted(enriched,key=lambda r:str(r.get("start_time") or r.get("target_date") or ""),reverse=True)[:100],
        "largest_total_misses":sorted(enriched,key=lambda r:num(r.get("total_error")) or -1,reverse=True)[:20],
        "largest_margin_misses":sorted(enriched,key=lambda r:num(r.get("margin_error")) or -1,reverse=True)[:20],
        "excluded_snapshots":excluded[:200],
        "policy":{"source":"frozen pregame game prediction ledger","chronology_required":True,"missing_start_time_excluded":True,"post_tipoff_snapshots_excluded":True,"duplicate_event_snapshots_keep_latest_pregame":True,"pass_rows_retained":True,"pass_rows_not_counted_as_betting_wins":True,"calibration_uses_frozen_pick_probability":True,"closing_line_value":"not reported because verified closing lines are not frozen in this ledger","auto_model_changes":False},
    }
    for path in OUTPUTS:
        path.parent.mkdir(parents=True,exist_ok=True); json.dump(report,path.open("w",encoding="utf-8"),indent=2,allow_nan=False)
    print(json.dumps(report["summary"],indent=2)); return report


if __name__=="__main__": build()
