"""Snapshot, grade, and analyze ALT Streak candidates.

The archive freezes pregame inputs so later model changes cannot rewrite history.
Grading uses the cumulative player game-log warehouse. Every archived candidate
is assigned WIN, LOSS, PUSH, VOID, or PENDING and one-unit profit/loss at its
listed American odds. Missing actuals and missing prices remain explicit.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ALT = Path("data/dashboard/wnba_alt_streaks.json")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
REPORTS = [Path("data/warehouse/wnba_alt_performance.json"), Path("data/dashboard/wnba_alt_performance.json")]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    output=[]
    if path.exists():
        for line in path.open(encoding="utf-8"):
            try:
                row=json.loads(line)
                if isinstance(row,dict): output.append(row)
            except Exception:
                pass
    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(clean(row),separators=(",",":"),allow_nan=False)+"\n")


def clean(value: Any) -> Any:
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [clean(v) for v in value]
    if isinstance(value,float): return value if math.isfinite(value) else None
    if value is None or isinstance(value,(str,int,bool)): return value
    return str(value)


def num(value: Any) -> float | None:
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’","'").split())


def candidate_id(row: dict[str,Any], target: str) -> str:
    parts=(target,row.get("player"),row.get("game"),row.get("stat"),row.get("side"),row.get("alt_line"),row.get("best_book"),row.get("best_odds"))
    return "|".join(norm(v) for v in parts)


def snapshot(target: str) -> dict[str,int]:
    payload=load(ALT,{"rows":[]})
    history=read_jsonl(ARCHIVE)
    existing={str(r.get("candidate_id")) for r in history}
    added=duplicates=0
    frozen_fields=(
        "player","team","game","opponent","stat","side","alt_line","line_type","streak",
        "l5_hits","l5_games","l5_pct","l10_hits","l10_games","l10_pct","season_hits","season_games","season_pct",
        "average","recent_values","best_odds","best_book","streak_score","streak_grade","streak_confidence",
        "streak_action","expected_edge","risk_level","score_components","score_weights","score_explanation",
        "opponent_rank","opponent_rank_total_teams","opponent_label","opponent_rank_source","opponent_rank_definition",
    )
    for source in payload.get("rows",[]):
        if not isinstance(source,dict): continue
        cid=candidate_id(source,target)
        if cid in existing:
            duplicates+=1; continue
        row={field:clean(source.get(field)) for field in frozen_fields}
        row.update({
            "candidate_id":cid,"date":target,"snapshot_at_utc":datetime.now(timezone.utc).isoformat(),
            "outcome":"PENDING","actual":None,"profit_loss":None,"graded_at_utc":None,
            "closing_line":None,"closing_odds":None,"clv_line":None,"clv_price":None,
            "archive_schema_version":"1.0",
        })
        history.append(row);existing.add(cid);added+=1
    write_jsonl(ARCHIVE,history)
    return {"added":added,"duplicates":duplicates,"total":len(history)}


def stat_value(record: dict[str,Any], stat: str) -> float | None:
    key=str(stat or "").upper().replace("THREES","3PM").replace(" ","_")
    s=record.get("scoring",{}) if isinstance(record.get("scoring"),dict) else {}
    b=record.get("boxscore",{}) if isinstance(record.get("boxscore"),dict) else {}
    f=record.get("fouls",{}) if isinstance(record.get("fouls"),dict) else {}
    d=record.get("derived",{}) if isinstance(record.get("derived"),dict) else {}
    values={
        "PTS":s.get("total_pts"),"Q1_PTS":s.get("q1_pts"),"Q2_PTS":s.get("q2_pts"),"Q3_PTS":s.get("q3_pts"),"Q4_PTS":s.get("q4_pts"),
        "1H_PTS":s.get("first_half_pts"),"2H_PTS":s.get("second_half_pts"),"FTM":s.get("ftm"),"FTA":s.get("fta"),
        "FT_PTS":s.get("free_throw_points"),"3PM":s.get("three_pm"),"REB":b.get("reb"),"OREB":b.get("oreb"),"DREB":b.get("dreb"),
        "AST":b.get("ast"),"STL":b.get("stl"),"BLK":b.get("blk"),"TOV":b.get("tov"),"PF":f.get("total_committed"),
        "SHOOTING_FOULS":f.get("shooting"),"OFFENSIVE_FOULS":f.get("offensive"),"TECHNICAL_FOULS":f.get("technical"),
        "FLAGRANT_FOULS":f.get("flagrant"),"PRA":d.get("pra"),"PR":d.get("pr"),"PA":d.get("pa"),"RA":d.get("ra"),
    }
    return num(values.get(key))


def outcome(side: str, actual: float | None, line: float | None) -> str:
    if actual is None or line is None: return "PENDING"
    if actual==line: return "PUSH"
    if str(side).upper()=="OVER": return "WIN" if actual>line else "LOSS"
    if str(side).upper()=="UNDER": return "WIN" if actual<line else "LOSS"
    return "VOID"


def one_unit_profit(result: str, odds: Any) -> float | None:
    price=num(odds)
    if result in {"PUSH","VOID"}: return 0.0
    if result=="PENDING": return None
    if result=="LOSS": return -1.0
    if price is None or price==0: return None
    return round(100/abs(price),4) if price<0 else round(price/100,4)


def grade_all() -> dict[str,int]:
    history=read_jsonl(ARCHIVE)
    logs=load(LOGS,{"records":[]})
    index: dict[tuple[str,str],list[dict[str,Any]]]=defaultdict(list)
    for record in logs.get("records",[]):
        if not isinstance(record,dict): continue
        index[(norm(record.get("player")),str(record.get("game_date") or "")[:10])].append(record)
    counts={k:0 for k in ("WIN","LOSS","PUSH","VOID","PENDING")};newly=0
    for row in history:
        if row.get("outcome") in {"WIN","LOSS","PUSH","VOID"}:
            counts[row["outcome"]]+=1;continue
        candidates=index.get((norm(row.get("player")),str(row.get("date") or "")[:10]),[])
        if not candidates:
            row["grading_reason"]="player-game actual unavailable";counts["PENDING"]+=1;continue
        record=candidates[0]
        actual=stat_value(record,str(row.get("stat") or ""))
        result=outcome(str(row.get("side") or ""),actual,num(row.get("alt_line")))
        row["actual"]=actual;row["outcome"]=result;row["profit_loss"]=one_unit_profit(result,row.get("best_odds"))
        row["graded_at_utc"]=datetime.now(timezone.utc).isoformat();row["actual_source"]="player_game_log_warehouse"
        row["grading_reason"]=None if result!="PENDING" else "actual stat unavailable"
        counts[result]+=1;newly+=result in {"WIN","LOSS","PUSH","VOID"}
    write_jsonl(ARCHIVE,history)
    return {"newly_graded":newly,**{k.lower():v for k,v in counts.items()}}


def group_summary(rows: list[dict[str,Any]], field: str) -> list[dict[str,Any]]:
    groups: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in rows: groups[str(row.get(field) or "Unknown")].append(row)
    output=[]
    for name,items in groups.items():
        wins=sum(r.get("outcome")=="WIN" for r in items);losses=sum(r.get("outcome")=="LOSS" for r in items)
        pushes=sum(r.get("outcome")=="PUSH" for r in items);decisions=wins+losses
        priced=[num(r.get("profit_loss")) for r in items if num(r.get("profit_loss")) is not None]
        pnl=sum(priced);risk=decisions
        output.append({"group":name,"candidates":len(items),"wins":wins,"losses":losses,"pushes":pushes,"decisions":decisions,
                       "hit_rate":round(wins/decisions,4) if decisions else None,"profit_loss_units":round(pnl,4),
                       "roi":round(pnl/risk,4) if risk else None})
    output.sort(key=lambda r:(r.get("roi") is not None,r.get("roi") or -999,r.get("decisions",0)),reverse=True)
    return output


def analyze(target: str) -> dict[str,Any]:
    rows=read_jsonl(ARCHIVE);graded=[r for r in rows if r.get("outcome") in {"WIN","LOSS","PUSH","VOID"}]
    wins=sum(r.get("outcome")=="WIN" for r in graded);losses=sum(r.get("outcome")=="LOSS" for r in graded);pushes=sum(r.get("outcome")=="PUSH" for r in graded)
    decisions=wins+losses;priced=[num(r.get("profit_loss")) for r in graded if num(r.get("profit_loss")) is not None];pnl=sum(priced)
    score_bands=[]
    for low,high,label in ((90,101,"90-100"),(85,90,"85-89.9"),(80,85,"80-84.9"),(75,80,"75-79.9"),(70,75,"70-74.9"),(60,70,"60-69.9"),(0,60,"Below 60")):
        subset=[r for r in graded if low <= (num(r.get("streak_score")) or -1) < high]
        if subset:
            for r in subset:r["_score_band"]=label
            score_bands.extend(group_summary(subset,"_score_band"))
    by_grade=group_summary(graded,"streak_grade");by_action=group_summary(graded,"streak_action");by_stat=group_summary(graded,"stat")
    by_side=group_summary(graded,"side");by_book=group_summary(graded,"best_book");by_rank_source=group_summary(graded,"opponent_rank_source")
    profitable=[r for r in score_bands if (r.get("decisions") or 0)>=20 and (r.get("roi") or 0)>0]
    threshold=max((r["group"] for r in profitable),default=None) if profitable else None
    report={
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),"target_date":target,"status":"ok",
        "summary":{"archived_candidates":len(rows),"graded":len(graded),"pending":sum(r.get("outcome")=="PENDING" for r in rows),
                   "wins":wins,"losses":losses,"pushes":pushes,"hit_rate":round(wins/decisions,4) if decisions else None,
                   "profit_loss_units":round(pnl,4),"roi":round(pnl/decisions,4) if decisions else None,
                   "recommended_minimum_score_band":threshold,"calibration_ready":decisions>=100},
        "by_grade":by_grade,"by_action":by_action,"by_score_band":score_bands,"by_stat":by_stat,"by_side":by_side,
        "by_sportsbook":by_book,"by_matchup_rank_source":by_rank_source,
        "recent_results":sorted(graded,key=lambda r:str(r.get("date") or ""),reverse=True)[:100],
        "policy":{"unit_size":1.0,"profit_basis":"listed American odds at snapshot","minimum_threshold_sample":20,
                  "recalibration_minimum_decisions":100,"closing_line_policy":"blank until verified closing market snapshot exists"},
    }
    for path in REPORTS:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("w",encoding="utf-8") as handle:json.dump(clean(report),handle,indent=2,allow_nan=False)
    return report


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--date",default=str(date.today()));parser.add_argument("--snapshot",action="store_true");parser.add_argument("--grade",action="store_true");parser.add_argument("--analyze",action="store_true");args=parser.parse_args()
    run_all=not any((args.snapshot,args.grade,args.analyze))
    if args.grade or run_all: print("ALT grade:",grade_all())
    if args.snapshot or run_all: print("ALT snapshot:",snapshot(args.date))
    if args.analyze or run_all: print("ALT analytics:",analyze(args.date)["summary"])


if __name__=="__main__": main()
