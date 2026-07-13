"""Immutable Model Picks Ledger.

Archives published model picks, enriches them with explainability and CLV, grades
results from the projection history warehouse, and produces searchable flat-unit
performance analytics. This tracks model performance only, not personal wagers.
"""
from __future__ import annotations
import argparse,json,math,statistics
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from typing import Any

TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
EXPLAIN=Path('data/dashboard/wnba_model_explainability.json')
MARKET=Path('data/dashboard/wnba_market_intelligence.json')
PROJECTION_HISTORY=Path('data/history/wnba_projection_history.jsonl')
LEDGER=Path('data/history/wnba_model_picks_ledger.jsonl')
OUTS=[Path('data/warehouse/wnba_model_picks_ledger.json'),Path('data/dashboard/wnba_model_picks_ledger.json')]
MODEL_VERSION='V4-PROJECTION-ENGINE-2'


def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def read_jsonl(path:Path)->list[dict[str,Any]]:
    out=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out

def write_jsonl(path:Path,rows:list[dict[str,Any]])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')

def dump(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    json.dump(payload,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)

def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def pick_id(target:str,row:dict[str,Any])->str:
    return '|'.join([target,norm(row.get('player')),norm(row.get('game')),str(row.get('stat') or ''),str(row.get('side') or ''),str(row.get('line') or ''),str(row.get('sportsbook') or '')])

def decimal(odds:Any)->float|None:
    value=num(odds)
    if value is None or value==0:return None
    return 1+100/-value if value<0 else 1+value/100

def projection_index()->dict[tuple[str,str,str],dict[str,Any]]:
    out={}
    for row in read_jsonl(PROJECTION_HISTORY):
        key=(str(row.get('date')),norm(row.get('player')),str(row.get('stat')))
        if row.get('actual') is not None:out[key]=row
    return out

def explanation_index()->dict[str,dict[str,Any]]:
    return {str(r.get('rank')):r for r in load(EXPLAIN,{'explanations':[]}).get('explanations',[]) if isinstance(r,dict)}

def clv_index()->dict[str,dict[str,Any]]:
    records=load(MARKET,{'records':[]}).get('records',[])
    out={}
    for r in records:
        key='|'.join([str(r.get('target_date')),norm(r.get('player')),norm(r.get('game')),str(r.get('stat') or ''),str(r.get('side') or ''),str(r.get('sportsbook') or '')])
        out[key]=r
    return out

def unified_index()->dict[str,dict[str,Any]]:
    return {norm(r.get('player')):r for r in load(UNIFIED,{'players':[]}).get('players',[]) if isinstance(r,dict) and r.get('player')}

def archive(target:str)->dict[str,int]:
    top=load(TOP,{'top_plays':[]});rows=read_jsonl(LEDGER);seen={r.get('pick_id') for r in rows};explain=explanation_index();unified=unified_index();added=0;now=datetime.now(timezone.utc).isoformat()
    for play in top.get('top_plays',[]):
        if play.get('decision') not in {'BET','LEAN'}:continue
        pid=pick_id(target,play)
        if pid in seen:continue
        player=unified.get(norm(play.get('player')),{});stat=str(play.get('stat') or '');dist=(player.get('distributions') or {}).get(stat,{})
        why=explain.get(str(play.get('rank')),{})
        rows.append({'pick_id':pid,'date':target,'archived_at_utc':now,'immutable':True,'player':play.get('player'),'team':play.get('team'),'opponent':play.get('opponent'),'game':play.get('game'),'market_type':play.get('market_type'),'stat':stat,'side':play.get('side'),'line':play.get('line'),'odds':play.get('odds'),'sportsbook':play.get('sportsbook'),'projection':dist.get('mean'),'projection_p10':dist.get('p10'),'projection_p50':dist.get('p50'),'projection_p90':dist.get('p90'),'hit_probability':play.get('hit_probability'),'expected_value_per_unit':play.get('expected_value_per_unit'),'confidence':play.get('confidence'),'top_play_score':play.get('top_play_score'),'decision':play.get('decision'),'flat_unit_stake':1.0,'recommended_units_reference':play.get('recommended_units_final'),'model_version':MODEL_VERSION,'explanation_summary':why.get('summary'),'opening_line':None,'closing_line':None,'line_clv':None,'movement_classification':None,'actual':None,'projection_error':None,'outcome':'PENDING','profit_loss':None});seen.add(pid);added+=1
    write_jsonl(LEDGER,rows);return {'added':added,'total':len(rows)}

def enrich_and_grade()->dict[str,int]:
    rows=read_jsonl(LEDGER);actuals=projection_index();clv=clv_index();graded=updated=0
    for row in rows:
        clv_key='|'.join([str(row.get('date')),norm(row.get('player')),norm(row.get('game')),str(row.get('stat') or ''),str(row.get('side') or ''),str(row.get('sportsbook') or '')])
        market=clv.get(clv_key)
        if market:
            row['opening_line']=market.get('opening_line');row['closing_line']=market.get('closing_line');row['line_clv']=market.get('line_clv');row['odds_clv_probability']=market.get('odds_clv_probability');row['movement_classification']=market.get('movement_classification');row['market_efficiency_score']=market.get('market_efficiency_score');updated+=1
        actual=actuals.get((str(row.get('date')),norm(row.get('player')),str(row.get('stat'))))
        if not actual or row.get('outcome')!='PENDING':continue
        value=num(actual.get('actual'));line=num(row.get('line'));projection=num(row.get('projection'))
        if value is None or line is None:continue
        if value==line:outcome='PUSH';profit=0.0
        else:
            win=value>line if str(row.get('side')).upper()=='OVER' else value<line
            outcome='WIN' if win else 'LOSS';d=decimal(row.get('odds'));profit=(d-1) if win and d is not None else -1.0
        row['actual']=value;row['projection_error']=round((projection-value),4) if projection is not None else None;row['absolute_projection_error']=round(abs(projection-value),4) if projection is not None else None;row['outcome']=outcome;row['profit_loss']=round(profit,4);row['graded_at_utc']=datetime.now(timezone.utc).isoformat();graded+=1
    write_jsonl(LEDGER,rows);return {'graded':graded,'clv_enriched':updated,'total':len(rows)}

def summarize(rows:list[dict[str,Any]])->dict[str,Any]:
    graded=[r for r in rows if r.get('outcome') in {'WIN','LOSS','PUSH'}];decisions=[r for r in graded if r.get('outcome') in {'WIN','LOSS'}];clvs=[num(r.get('line_clv')) for r in rows];clvs=[x for x in clvs if x is not None]
    return {'picks':len(rows),'graded':len(graded),'pending':sum(r.get('outcome')=='PENDING' for r in rows),'wins':sum(r.get('outcome')=='WIN' for r in rows),'losses':sum(r.get('outcome')=='LOSS' for r in rows),'pushes':sum(r.get('outcome')=='PUSH' for r in rows),'win_rate':round(sum(r.get('outcome')=='WIN' for r in decisions)/len(decisions),4) if decisions else None,'profit_loss':round(sum(num(r.get('profit_loss')) or 0 for r in graded),4),'roi':round(sum(num(r.get('profit_loss')) or 0 for r in graded)/len(graded),4) if graded else None,'average_clv':round(sum(clvs)/len(clvs),4) if clvs else None,'positive_clv_rate':round(sum(x>0 for x in clvs)/len(clvs),4) if clvs else None,'mae':round(sum(num(r.get('absolute_projection_error')) or 0 for r in graded)/sum(r.get('absolute_projection_error') is not None for r in graded),4) if any(r.get('absolute_projection_error') is not None for r in graded) else None}

def aggregate(rows:list[dict[str,Any]],field:str)->list[dict[str,Any]]:
    groups=defaultdict(list)
    for r in rows:groups[str(r.get(field) or 'Unknown')].append(r)
    return sorted([{'group':k,**summarize(v)} for k,v in groups.items()],key=lambda r:(r['graded'],r['picks']),reverse=True)

def confidence_tier(v:Any)->str:
    x=num(v) or 0
    return '90-100' if x>=90 else '80-89' if x>=80 else '70-79' if x>=70 else 'Below 70'

def window(rows:list[dict[str,Any]],days:int,target:str)->dict[str,Any]:
    try:end=date.fromisoformat(target)
    except Exception:end=date.today()
    start=end-timedelta(days=days-1)
    subset=[]
    for r in rows:
        try:d=date.fromisoformat(str(r.get('date')))
        except Exception:continue
        if start<=d<=end:subset.append(r)
    return {'days':days,**summarize(subset)}

def daily_reports(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    groups=defaultdict(list)
    for r in rows:groups[str(r.get('date'))].append(r)
    out=[]
    for day,items in groups.items():
        misses=sorted([r for r in items if r.get('outcome')=='LOSS'],key=lambda r:num(r.get('absolute_projection_error')) or 0,reverse=True)[:3]
        wins=sorted([r for r in items if r.get('outcome')=='WIN'],key=lambda r:num(r.get('profit_loss')) or 0,reverse=True)[:3]
        out.append({'date':day,**summarize(items),'top_wins':[r.get('pick_id') for r in wins],'biggest_misses':[r.get('pick_id') for r in misses]})
    return sorted(out,key=lambda r:r['date'],reverse=True)

def analyze(target:str)->dict[str,Any]:
    rows=read_jsonl(LEDGER)
    decorated=[{**r,'confidence_tier':confidence_tier(r.get('confidence'))} for r in rows]
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':summarize(rows),'windows':[window(rows,d,target) for d in (7,14,30)],'by_stat':aggregate(decorated,'stat'),'by_player':aggregate(decorated,'player'),'by_team':aggregate(decorated,'team'),'by_sportsbook':aggregate(decorated,'sportsbook'),'by_confidence_tier':aggregate(decorated,'confidence_tier'),'by_model_version':aggregate(decorated,'model_version'),'by_month':aggregate([{**r,'month':str(r.get('date'))[:7]} for r in decorated],'month'),'daily_reports':daily_reports(rows),'recent_picks':sorted(rows,key=lambda r:(str(r.get('date')),str(r.get('archived_at_utc'))),reverse=True)[:100],'policy':{'personal_wagers_tracked':False,'flat_unit_evaluation':True,'immutable_archive':True,'duplicate_pick_ids_allowed':False,'actual_source':'wnba_projection_history.jsonl','clv_source':'wnba_market_intelligence.json'}}
    for path in OUTS:dump(path,payload)
    print('Model Picks Ledger:',payload['summary']);return payload

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('archive','grade','analyze','all'));parser.add_argument('--date',default=str(date.today()));args=parser.parse_args()
    if args.mode in {'archive','all'}:print('archive',archive(args.date))
    if args.mode in {'grade','all'}:print('grade',enrich_and_grade())
    if args.mode in {'analyze','all'}:analyze(args.date)
if __name__=='__main__':main()
