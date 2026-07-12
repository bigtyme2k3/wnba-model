"""M21 probability calibration from finalized model history."""
from __future__ import annotations
import argparse,json,math,os
from datetime import date,datetime,timezone
HIST='data/history/wnba_model_history.jsonl'
def read_jsonl(path):
    out=[]
    if os.path.exists(path):
        for line in open(path,encoding='utf-8'):
            try: out.append(json.loads(line))
            except Exception: pass
    return out
def clamp(x,a,b): return max(a,min(b,x))
def build(target):
    rows=[]
    for r in read_jsonl(HIST):
        if r.get('outcome') not in {'WIN','LOSS'}: continue
        p=r.get('simulation_probability',r.get('probability',r.get('confidence')))
        try:
            p=float(p); p=p/100 if p>1 else p
            if not math.isfinite(p): continue
        except Exception: continue
        rows.append((clamp(p,0.001,0.999),1 if r.get('outcome')=='WIN' else 0))
    buckets=[]; ece=0.0
    for lo in [0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9]:
        hi=1.01 if lo==0.9 else lo+0.05; vals=[x for x in rows if lo<=x[0]<hi]
        if not vals: continue
        conf=sum(x[0] for x in vals)/len(vals); hit=sum(x[1] for x in vals)/len(vals); gap=hit-conf; ece+=abs(gap)*len(vals)/max(1,len(rows))
        buckets.append({'low':lo,'high':1.0 if hi>1 else hi,'count':len(vals),'avg_confidence':round(conf,4),'hit_rate':round(hit,4),'gap':round(gap,4)})
    brier=sum((p-y)**2 for p,y in rows)/max(1,len(rows)); correction=round(sum((b['hit_rate']-b['avg_confidence'])*b['count'] for b in buckets)/max(1,len(rows)),4) if buckets else 0
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'samples':len(rows),'brier_score':round(brier,5),'ece':round(ece,5),'calibration_offset':correction,'minimum_sample_met':len(rows)>=50},'buckets':buckets,'policy':{'minimum_samples':50,'max_confidence_adjustment':0.05}}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_model_calibration.json','data/dashboard/wnba_model_calibration.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Calibration:',build(a.date)['summary'])
if __name__=='__main__':main()
