from __future__ import annotations
import argparse, hashlib, json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB=Path('data/warehouse/wnba_forward_validation.sqlite')
DASH=Path('data/dashboard')
WARE=Path('data/warehouse')
OUTS=[DASH/'wnba_forward_validation.json',WARE/'wnba_forward_validation.json']
SOURCES=[('daily_edge',DASH/'wnba_daily_edges.json','top_edges'),('ensemble',DASH/'wnba_ensemble_intelligence.json','ranked_edges'),('simulation',DASH/'wnba_monte_carlo_scenarios.json','ranked_simulations')]

def load(p:Path,d:Any):
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d

def num(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def norm(v):return ' '.join(str(v or '').strip().lower().split())

def key(source,r):
    raw='|'.join(map(str,[source,r.get('target_date'),r.get('game'),r.get('player'),r.get('market') or r.get('stat'),r.get('side') or r.get('model_signal'),r.get('line'),r.get('sportsbook')]))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS forward_predictions(
    prediction_id TEXT PRIMARY KEY, source TEXT, target_date TEXT, frozen_at_utc TEXT,
    game TEXT, player TEXT, market TEXT, side TEXT, line REAL, sportsbook TEXT, odds REAL,
    edge_score REAL, ensemble_score REAL, model_probability REAL, simulation_probability REAL,
    payload_json TEXT, result TEXT, actual_value REAL, graded_at_utc TEXT, profit_units REAL,
    chronology_valid INTEGER DEFAULT 1, UNIQUE(source,target_date,game,player,market,side,line,sportsbook))''')
    conn.commit()

def freeze(target_date:str)->dict:
    DB.parent.mkdir(parents=True,exist_ok=True);conn=sqlite3.connect(DB);ensure(conn)
    now=datetime.now(timezone.utc).isoformat();inserted=0;existing=0;by={}
    for source,path,field in SOURCES:
        data=load(path,{})
        rows=data.get(field,[]) if isinstance(data,dict) else []
        count=0
        for r in rows:
            if not isinstance(r,dict):continue
            td=str(r.get('target_date') or data.get('target_date') or target_date)
            if target_date and td and td!=target_date:continue
            pid=key(source,{**r,'target_date':td})
            vals=(pid,source,td,now,r.get('game'),r.get('player'),r.get('market') or r.get('stat'),str(r.get('side') or r.get('model_signal') or '').upper(),num(r.get('line')),r.get('sportsbook'),num(r.get('odds')),num(r.get('edge_score')),num(r.get('ensemble_score')),num(r.get('calibrated_probability') or r.get('adaptive_probability') or r.get('model_probability')),num(r.get('simulation_probability') or r.get('signal_probability')),json.dumps(r,separators=(',',':'),allow_nan=False))
            cur=conn.execute('''INSERT OR IGNORE INTO forward_predictions(prediction_id,source,target_date,frozen_at_utc,game,player,market,side,line,sportsbook,odds,edge_score,ensemble_score,model_probability,simulation_probability,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',vals)
            if cur.rowcount:inserted+=1;count+=1
            else:existing+=1
        by[source]=count
    conn.commit();conn.close()
    return {'mode':'freeze','target_date':target_date,'inserted':inserted,'existing':existing,'by_source':by,'frozen_at_utc':now}

def result_rows():
    data=load(DASH/'wnba_results_grading.json',{})
    rows=[]
    for field in ('graded_props','results','rows','grades'):
        if isinstance(data.get(field),list):rows.extend(data[field])
    return rows

def profit(result,odds):
    if result=='LOSS':return -1.0
    if result in {'PUSH','VOID'}:return 0.0
    if result!='WIN':return None
    return (odds/100 if odds and odds>0 else 100/abs(odds) if odds else .9091)

def grade(target_date:str)->dict:
    DB.parent.mkdir(parents=True,exist_ok=True);conn=sqlite3.connect(DB);conn.row_factory=sqlite3.Row;ensure(conn)
    grades=result_rows();matched=0
    for g in grades:
        player=norm(g.get('player') or g.get('player_name'));market=norm(g.get('market') or g.get('stat') or g.get('prop_type'));side=str(g.get('side') or g.get('selection') or '').upper();line=num(g.get('line'));actual=num(g.get('actual') or g.get('actual_value') or g.get('value'));result=str(g.get('result') or g.get('grade') or '').upper()
        if result not in {'WIN','LOSS','PUSH','VOID'}:continue
        q='''SELECT prediction_id,odds FROM forward_predictions WHERE result IS NULL AND lower(trim(player))=? AND lower(trim(market))=?''';args=[player,market]
        if target_date:q+=' AND target_date=?';args.append(target_date)
        rows=conn.execute(q,args).fetchall()
        for r in rows:
            conn.execute('UPDATE forward_predictions SET result=?,actual_value=?,graded_at_utc=?,profit_units=? WHERE prediction_id=?',(result,actual,datetime.now(timezone.utc).isoformat(),profit(result,num(r['odds'])),r['prediction_id']));matched+=1
    conn.commit();conn.close();return {'mode':'grade','target_date':target_date,'graded_predictions':matched}

def report()->dict:
    DB.parent.mkdir(parents=True,exist_ok=True);conn=sqlite3.connect(DB);conn.row_factory=sqlite3.Row;ensure(conn)
    rows=[dict(r) for r in conn.execute('SELECT * FROM forward_predictions').fetchall()];conn.close()
    settled=[r for r in rows if r.get('result') in {'WIN','LOSS','PUSH','VOID'}];dec=[r for r in settled if r['result'] in {'WIN','LOSS'}];wins=sum(r['result']=='WIN' for r in dec);units=sum(float(r.get('profit_units') or 0) for r in settled)
    by={}
    for source in sorted(set(r['source'] for r in rows)):
        s=[r for r in dec if r['source']==source];by[source]={'frozen':sum(r['source']==source for r in rows),'graded':len(s),'hit_rate':round(sum(r['result']=='WIN' for r in s)/len(s),4) if s else None}
    rep={'sprint':12,'phase':'live-forward-validation','generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'ok','summary':{'frozen_predictions':len(rows),'settled_predictions':len(settled),'decision_records':len(dec),'wins':wins,'losses':len(dec)-wins,'hit_rate':round(wins/len(dec),4) if dec else None,'units':round(units,3),'roi':round(units/len(dec),4) if dec else None,'chronology_valid':all(r.get('chronology_valid')==1 for r in rows)},'by_source':by,'recent_predictions':rows[-100:],'warning':'Only predictions frozen before outcomes are eligible for live-forward validation.'}
    for p in OUTS:p.parent.mkdir(parents=True,exist_ok=True);json.dump(rep,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(rep['summary'],indent=2));return rep

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['freeze','grade','both','report'],default='both');ap.add_argument('--date',default='');a=ap.parse_args();out={}
    if a.mode in {'freeze','both'}:out['freeze']=freeze(a.date)
    if a.mode in {'grade','both'}:out['grade']=grade(a.date)
    out['report']=report();print(json.dumps(out,indent=2))
if __name__=='__main__':main()
