from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

HIST='data/history/wnba_model_history.jsonl'

def read_rows():
    rows=[]
    if os.path.exists(HIST):
        for line in open(HIST,encoding='utf-8'):
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

def build(target):
    rows=read_rows()
    graded=[r for r in rows if r.get('outcome') in {'WIN','LOSS','PUSH'}]
    wins=sum(1 for r in graded if r.get('outcome')=='WIN')
    losses=sum(1 for r in graded if r.get('outcome')=='LOSS')
    by_stat={}
    for r in graded:
        stat=r.get('stat','UNK')
        d=by_stat.setdefault(stat,{'wins':0,'losses':0,'pushes':0})
        if r.get('outcome')=='WIN': d['wins']+=1
        elif r.get('outcome')=='LOSS': d['losses']+=1
        else: d['pushes']+=1
    for d in by_stat.values():
        d['win_rate']=round(d['wins']/max(1,d['wins']+d['losses']),4)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'history_rows':len(rows),'graded_rows':len(graded),'wins':wins,'losses':losses,'win_rate':round(wins/max(1,wins+losses),4)},'by_stat':by_stat,'recent_graded':graded[-50:]}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_backtest_engine.json','data/dashboard/wnba_backtest_engine.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Backtest engine built:', build(args.date)['summary'])
if __name__=='__main__': main()
