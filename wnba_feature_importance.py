"""M22 outcome-aware feature importance with drift tracking."""
from __future__ import annotations
import argparse,json,math,os
from datetime import date,datetime,timezone
HIST='data/history/wnba_model_history.jsonl'; PREV='data/warehouse/wnba_feature_importance.json'
FEATURES={'edge_pct':'Projection Edge','ev_pct':'Expected Value','market_move':'Market Movement','line_clv':'Closing Line Value','injury_confidence_penalty':'Injury Impact','rest_days':'Rest','pace_40':'Pace','matchup_score':'Matchup Rating','simulation_probability':'Simulation Probability'}
def read_jsonl(path):
    out=[]
    if os.path.exists(path):
        for line in open(path,encoding='utf-8'):
            try:out.append(json.loads(line))
            except Exception:pass
    return out
def load(path,d):
    try:return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else d
    except Exception:return d
def val(x):
    try:
        n=float(x);return n if math.isfinite(n) else None
    except Exception:return None
def corr(xs,ys):
    if len(xs)<5:return 0.0
    mx=sum(xs)/len(xs);my=sum(ys)/len(ys);num=sum((x-mx)*(y-my) for x,y in zip(xs,ys));dx=sum((x-mx)**2 for x in xs);dy=sum((y-my)**2 for y in ys)
    return num/math.sqrt(dx*dy) if dx and dy else 0.0
def build(target):
    rows=[r for r in read_jsonl(HIST) if r.get('outcome') in {'WIN','LOSS'}]; previous={x['feature']:x.get('importance',0) for x in load(PREV,{}).get('features',[])}; ranked=[]
    for field,name in FEATURES.items():
        pairs=[(val(r.get(field)),1 if r.get('outcome')=='WIN' else 0) for r in rows];pairs=[p for p in pairs if p[0] is not None]
        importance=abs(corr([p[0] for p in pairs],[p[1] for p in pairs]));ranked.append({'feature':name,'field':field,'samples':len(pairs),'importance':round(importance,5),'direction':'positive' if corr([p[0] for p in pairs],[p[1] for p in pairs])>=0 else 'negative','drift':round(importance-previous.get(name,importance),5)})
    ranked.sort(key=lambda x:x['importance'],reverse=True)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'graded_samples':len(rows),'features':len(ranked),'minimum_sample_met':len(rows)>=50},'features':ranked,'top_features':ranked[:5]}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_feature_importance.json','data/dashboard/wnba_feature_importance.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Feature importance:',build(a.date)['summary'])
if __name__=='__main__':main()
