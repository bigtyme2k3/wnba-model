"""
wnba_results_grader.py
----------------------
Grades historical model recommendations when actual player stat data is available.

Current data inputs are intentionally flexible:
- data/raw/player_results_<date>.csv
- data/raw/boxscore_player_stats_<date>.csv
- data/raw/wnba_boxscores_<date>.csv

Expected useful columns:
player, pts, reb, ast, threes/3pm, pra, pa, pr, ra

Outputs:
- data/warehouse/wnba_results_grading.json
- data/dashboard/wnba_results_grading.json
- updates data/history/wnba_model_history.jsonl with outcome/actual when possible
"""
from __future__ import annotations

import argparse, json, os
from datetime import date, datetime, timezone
from typing import Any, Dict, List
import pandas as pd

HISTORY_PATH="data/history/wnba_model_history.jsonl"


def norm(v): return str(v or "").strip().lower().replace("’", "'")
def sf(v, d=0.0):
    try:
        if v is None or str(v).lower()=="nan" or v=="": return d
        return float(v)
    except Exception: return d


def read_history():
    rows=[]
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except Exception: pass
    return rows


def write_history(rows):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH,"w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r,separators=(",",":"))+"\n")


def load_actuals(target):
    paths=[f"data/raw/player_results_{target}.csv",f"data/raw/boxscore_player_stats_{target}.csv",f"data/raw/wnba_boxscores_{target}.csv"]
    for p in paths:
        if os.path.exists(p):
            try:
                df=pd.read_csv(p)
                if not df.empty and "player" in df.columns:
                    print(f"Loaded actuals: {p} ({len(df)} rows)")
                    return df
            except Exception as exc: print(f"WARN actuals read failed {p}: {exc}")
    return pd.DataFrame()


def actual_value(row, stat):
    stat=str(stat or "").upper()
    pts=sf(row.get("pts", row.get("PTS",0)))
    reb=sf(row.get("reb", row.get("REB",0)))
    ast=sf(row.get("ast", row.get("AST",0)))
    th=sf(row.get("threes", row.get("3pm", row.get("3PM", row.get("fg3m",0)))))
    if stat=="PTS": return pts
    if stat=="REB": return reb
    if stat=="AST": return ast
    if stat=="3PM": return th
    if stat=="PRA": return pts+reb+ast
    if stat=="PA": return pts+ast
    if stat=="PR": return pts+reb
    if stat=="RA": return reb+ast
    return row.get(stat.lower())


def grade(signal, actual, line):
    if actual is None or line is None: return None
    signal=str(signal or "").upper()
    actual=sf(actual); line=sf(line)
    if actual==line: return "PUSH"
    if signal in {"OVER","YES"}: return "WIN" if actual>line else "LOSS"
    if signal in {"UNDER","NO"}: return "WIN" if actual<line else "LOSS"
    return None


def build(target):
    hist=read_history(); actuals=load_actuals(target); actual_map={}
    if not actuals.empty:
        for _,r in actuals.iterrows(): actual_map[norm(r.get("player"))]=r.to_dict()
    graded=0; wins=losses=pushes=0
    for r in hist:
        if r.get("date")!=target or r.get("outcome") in {"WIN","LOSS","PUSH"}: continue
        a=actual_map.get(norm(r.get("player")))
        if not a: continue
        val=actual_value(a, r.get("stat")); out=grade(r.get("signal"), val, r.get("line"))
        if out:
            r["actual"]=val; r["outcome"]=out; r["graded_at_utc"]=datetime.now(timezone.utc).isoformat(); graded+=1
            wins += 1 if out=="WIN" else 0; losses += 1 if out=="LOSS" else 0; pushes += 1 if out=="PUSH" else 0
    write_history(hist)
    total_dec=max(1,wins+losses)
    report={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"target_date":target,"actual_source_rows":len(actuals),"graded_this_run":graded,"wins":wins,"losses":losses,"pushes":pushes,"win_rate":round(wins/total_dec,4),"status":"ok" if graded else "waiting_for_actuals"}
    os.makedirs("data/warehouse",exist_ok=True); os.makedirs("data/dashboard",exist_ok=True)
    for p in ["data/warehouse/wnba_results_grading.json","data/dashboard/wnba_results_grading.json"]:
        with open(p,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
    return report


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date",default=str(date.today())); args=ap.parse_args(); print(f"✅ Results grading: {build(args.date)}")
if __name__=="__main__": main()
