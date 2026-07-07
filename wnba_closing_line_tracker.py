"""
wnba_closing_line_tracker.py
----------------------------
Stores line snapshots and calculates closing-line value when a closing snapshot exists.

Inputs:
- data/raw/player_points_<date>.csv
- data/history/wnba_model_history.jsonl

Outputs:
- data/history/wnba_line_snapshots.jsonl
- data/warehouse/wnba_clv_summary.json
- data/dashboard/wnba_clv_summary.json
"""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
import pandas as pd

SNAPS="data/history/wnba_line_snapshots.jsonl"; HIST="data/history/wnba_model_history.jsonl"

def sf(v,d=0.0):
    try:
        if v is None or str(v).lower()=="nan" or v=="": return d
        return float(v)
    except Exception: return d

def load_points(target):
    for p in [f"data/raw/player_points_{target}.csv","data/raw/player_points_today.csv"]:
        if os.path.exists(p):
            try: return pd.read_csv(p)
            except Exception: pass
    return pd.DataFrame()

def append_snapshot(target, stage):
    os.makedirs(os.path.dirname(SNAPS),exist_ok=True); df=load_points(target); now=datetime.now(timezone.utc).isoformat(); rows=[]
    if not df.empty:
        for _,r in df.iterrows():
            rows.append({"snapshot_key":f"{target}|{stage}|{r.get('player')}|{r.get('game')}|{r.get('stat')}|{r.get('line')}|{now}","date":target,"stage":stage,"captured_at_utc":now,"player":r.get("player"),"game":r.get("game"),"stat":r.get("stat"),"line":r.get("line"),"over_price":r.get("over_price"),"under_price":r.get("under_price"),"book":r.get("book",r.get("source"))})
    with open(SNAPS,"a",encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row,separators=(",",":"))+"\n")
    return rows

def read_jsonl(path):
    rows=[]
    if os.path.exists(path):
        with open(path,encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except Exception: pass
    return rows

def update_history_clv(target):
    hist=read_jsonl(HIST); snaps=[s for s in read_jsonl(SNAPS) if s.get("date")==target]
    if not hist or not snaps: return 0
    latest={}
    for s in snaps:
        k=(s.get("player"),s.get("game"),s.get("stat")); latest[k]=s
    changed=0
    for r in hist:
        if r.get("date")!=target: continue
        s=latest.get((r.get("player"),r.get("game"),r.get("stat")))
        if not s: continue
        open_line=sf(r.get("line"),None); close_line=sf(s.get("line"),None)
        if open_line is None or close_line is None: continue
        sig=str(r.get("signal","")).upper()
        clv=(close_line-open_line) if sig in {"OVER","YES"} else (open_line-close_line)
        r["closing_line"]=close_line; r["clv"]=round(clv,2); changed+=1
    if changed:
        with open(HIST,"w",encoding="utf-8") as f:
            for r in hist: f.write(json.dumps(r,separators=(",",":"))+"\n")
    return changed

def build(target, stage):
    rows=append_snapshot(target,stage); changed=update_history_clv(target); snaps=[s for s in read_jsonl(SNAPS) if s.get("date")==target]
    report={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"target_date":target,"stage":stage,"snapshot_rows_added":len(rows),"total_snapshots_for_date":len(snaps),"history_clv_updates":changed,"status":"ok" if rows else "no_lines"}
    os.makedirs("data/warehouse",exist_ok=True); os.makedirs("data/dashboard",exist_ok=True)
    for p in ["data/warehouse/wnba_clv_summary.json","data/dashboard/wnba_clv_summary.json"]:
        with open(p,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date",default=str(date.today())); ap.add_argument("--stage",default="snapshot"); args=ap.parse_args(); print(f"✅ CLV tracker: {build(args.date,args.stage)}")
if __name__=="__main__": main()
