"""
wnba_betting_ledger.py
----------------------
Maintains a recommended-card ledger. It does not place bets; it records model
recommendations and optional manual stake results.

Outputs:
- data/history/wnba_betting_ledger.jsonl
- data/warehouse/wnba_betting_ledger_summary.json
- data/dashboard/wnba_betting_ledger_summary.json
"""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
from typing import Any

LEDGER="data/history/wnba_betting_ledger.jsonl"

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,encoding="utf-8") as f: return json.load(f)
    except Exception: pass
    return d

def read_jsonl(p):
    rows=[]
    if os.path.exists(p):
        with open(p,encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except Exception: pass
    return rows

def american_profit(stake, odds):
    try: odds=float(odds); stake=float(stake)
    except Exception: return 0
    return stake*(odds/100) if odds>0 else stake*(100/abs(odds))

def build(target, unit=20.0):
    cons=load_json("data/warehouse/wnba_consensus_engine.json",{})
    existing=read_jsonl(LEDGER); seen={r.get("ledger_key") for r in existing}; new=[]; now=datetime.now(timezone.utc).isoformat()
    for r in cons.get("top_consensus",[]) if isinstance(cons,dict) else []:
        if r.get("recommendation") not in {"BET","LEAN"}: continue
        k=f"{target}|{r.get('player')}|{r.get('game')}|{r.get('stat')}|{r.get('line')}|{r.get('signal')}"
        if k in seen: continue
        stake=unit if r.get("recommendation")=="BET" else round(unit*0.5,2)
        new.append({"ledger_key":k,"date":target,"created_at_utc":now,"player":r.get("player"),"team":r.get("team"),"game":r.get("game"),"stat":r.get("stat"),"line":r.get("line"),"signal":r.get("signal"),"recommendation":r.get("recommendation"),"consensus_score":r.get("consensus_score"),"engine_agreement":r.get("engine_agreement"),"stake":stake,"unit_size":unit,"odds":-110,"status":"OPEN","result":None,"profit":None,"book":"manual/best available","notes":"Model recommendation record; manually confirm odds before betting."})
    os.makedirs(os.path.dirname(LEDGER),exist_ok=True)
    if new:
        with open(LEDGER,"a",encoding="utf-8") as f:
            for r in new: f.write(json.dumps(r,separators=(",",":"))+"\n")
    rows=read_jsonl(LEDGER); settled=[r for r in rows if r.get("status")=="SETTLED"]
    profit=sum(float(r.get("profit") or 0) for r in settled)
    risk=sum(float(r.get("stake") or 0) for r in rows if r.get("status")=="OPEN")
    report={"generated_at_utc":now,"target_date":target,"new_records":len(new),"total_records":len(rows),"open_risk":round(risk,2),"settled_records":len(settled),"profit":round(profit,2),"roi":round(profit/max(1,sum(float(r.get('stake') or 0) for r in settled)),4),"recent":rows[-50:]}
    os.makedirs("data/warehouse",exist_ok=True); os.makedirs("data/dashboard",exist_ok=True)
    for p in ["data/warehouse/wnba_betting_ledger_summary.json","data/dashboard/wnba_betting_ledger_summary.json"]:
        with open(p,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date",default=str(date.today())); ap.add_argument("--unit",type=float,default=20.0); args=ap.parse_args(); print(f"✅ Betting ledger: {build(args.date,args.unit)}")
if __name__=="__main__": main()
