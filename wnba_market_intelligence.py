"""CLV, line movement, market efficiency, and historical intelligence.

Every run appends immutable market observations for the current Top Plays board.
The first observation is the opening snapshot, the first actionable recommendation
is the recommendation snapshot, and the latest pregame observation becomes the
closing snapshot. Lines are evaluated from the bettor's side so positive CLV
always means the captured number was better than the close.
"""
from __future__ import annotations
import argparse,json,math,statistics
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
EXPLAIN=Path('data/dashboard/wnba_model_explainability.json')
PROJECTION_HISTORY=Path('data/history/wnba_projection_history.jsonl')
OBS=Path('data/history/wnba_market_observations.jsonl')
OUTS=[Path('data/warehouse/wnba_market_intelligence.json'),Path('data/dashboard/wnba_market_intelligence.json')]
MODEL_VERSION='V4-PROJECTION-ENGINE-2'

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def read_jsonl(p:Path)->list[dict[str,Any]]:
    out=[]
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out
def write_jsonl(p:Path,rows:list[dict[str,Any]])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def market_id(target:str,row:dict[str,Any])->str:
    return '|'.join([target,norm(row.get('player')),norm(row.get('game')),str(row.get('stat') or ''),str(row.get('side') or ''),str(row.get('sportsbook') or '')])
def decimal(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return 1+100/-x if x<0 else 1+x/100
def implied(o:Any)->float|None:
    d=decimal(o);return None if d is None else 1/d
def side_line_value(side:str,line:float)->float:
    return line if str(side).upper()=='UNDER' else -line
def line_clv(side:str,recommendation:float,closing:float)->float:
    return side_line_value(side,recommendation)-side_line_value(side,closing)
def odds_clv(recommendation:Any,closing:Any)->float|None:
    rp=implied(recommendation);cp=implied(closing)
    return None if rp is None or cp is None else cp-rp
def explanation_map()->dict[str,dict[str,Any]]:
    payload=load(EXPLAIN,{'explanations':[]})
    return {str(r.get('rank')):r for r in payload.get('explanations',[]) if isinstance(r,dict)}
def capture(target:str,stage:str='current')->dict[str,int]:
    top=load(TOP,{'top_plays':[]});existing=read_jsonl(OBS);explanations=explanation_map();now=datetime.now(timezone.utc).isoformat();added=0
    fingerprint={(r.get('market_id'),r.get('captured_at_utc'),r.get('line'),r.get('odds')) for r in existing}
    for row in top.get('top_plays',[]):
        line=num(row.get('line'));odds=num(row.get('odds'))
        if line is None or odds is None:continue
        mid=market_id(target,row);key=(mid,now,line,odds)
        if key in fingerprint:continue
        recs=[r for r in existing if r.get('market_id')==mid]
        observation_stage='opening' if not recs else 'recommendation' if row.get('decision') in {'BET','LEAN'} and not any(r.get('stage')=='recommendation' for r in recs) else stage
        explanation=explanations.get(str(row.get('rank')),{})
        existing.append({'observation_id':f'{mid}|{now}','market_id':mid,'target_date':target,'captured_at_utc':now,'stage':observation_stage,'player':row.get('player'),'team':row.get('team'),'opponent':row.get('opponent'),'game':row.get('game'),'market_type':row.get('market_type'),'stat':row.get('stat'),'side':row.get('side'),'line':line,'odds':odds,'sportsbook':row.get('sportsbook'),'rank':row.get('rank'),'decision':row.get('decision'),'confidence':row.get('confidence'),'expected_value_per_unit':row.get('expected_value_per_unit'),'hit_probability':row.get('hit_probability'),'recommended_units':row.get('recommended_units_final'),'model_version':MODEL_VERSION,'explanation_summary':explanation.get('summary'),'immutable':True});added+=1
    write_jsonl(OBS,existing);return {'added':added,'total':len(existing)}
def actual_index()->dict[tuple[str,str,str],dict[str,Any]]:
    rows=read_jsonl(PROJECTION_HISTORY);out={}
    for r in rows:
        if r.get('actual') is not None:out[(str(r.get('date')),norm(r.get('player')),str(r.get('stat')))] = r
    return out
def classify_movement(side:str,opening:float,recommendation:float,closing:float,model_projection:float|None=None)->str:
    toward=line_clv(side,recommendation,closing)>0
    total_move=abs(closing-opening)
    if total_move>=2 and toward:return 'STEAM_TOWARD_MODEL'
    if total_move>=2 and not toward:return 'STEAM_AWAY_FROM_MODEL'
    if model_projection is not None:
        model_side='OVER' if model_projection>recommendation else 'UNDER'
        market_side='OVER' if closing>opening else 'UNDER'
        if model_side!=market_side and total_move>=1:return 'REVERSE_LINE_MOVEMENT'
    if total_move>=1:return 'MEANINGFUL_MOVE'
    return 'STABLE'
def aggregate(records:list[dict[str,Any]],field:str)->list[dict[str,Any]]:
    groups=defaultdict(list)
    for r in records:groups[str(r.get(field) or 'Unknown')].append(r)
    out=[]
    for group,rows in groups.items():
        clvs=[num(r.get('line_clv')) for r in rows];clvs=[x for x in clvs if x is not None]
        odds=[num(r.get('odds_clv_probability')) for r in rows];odds=[x for x in odds if x is not None]
        graded=[r for r in rows if r.get('outcome') in {'WIN','LOSS','PUSH'}]
        out.append({'group':group,'count':len(rows),'average_line_clv':round(sum(clvs)/len(clvs),4) if clvs else None,'positive_clv_rate':round(sum(x>0 for x in clvs)/len(clvs),4) if clvs else None,'average_odds_clv':round(sum(odds)/len(odds),4) if odds else None,'wins':sum(r.get('outcome')=='WIN' for r in graded),'losses':sum(r.get('outcome')=='LOSS' for r in graded),'roi':round(sum(num(r.get('profit_loss')) or 0 for r in graded)/len(graded),4) if graded else None})
    return sorted(out,key=lambda r:(r['count'],r.get('average_line_clv') or -999),reverse=True)
def analyze(target:str)->dict[str,Any]:
    observations=read_jsonl(OBS);actuals=actual_index();groups=defaultdict(list)
    for r in observations:groups[r.get('market_id')].append(r)
    records=[]
    for mid,rows in groups.items():
        rows=sorted(rows,key=lambda r:r.get('captured_at_utc') or '')
        opening=rows[0];recommendation=next((r for r in rows if r.get('stage')=='recommendation'),rows[0]);closing=rows[-1]
        side=str(recommendation.get('side') or '');rec_line=num(recommendation.get('line'));close_line=num(closing.get('line'));open_line=num(opening.get('line'))
        if None in (rec_line,close_line,open_line):continue
        actual=actuals.get((str(recommendation.get('target_date')),norm(recommendation.get('player')),str(recommendation.get('stat'))),{})
        clv=line_clv(side,rec_line,close_line);oclv=odds_clv(recommendation.get('odds'),closing.get('odds'))
        timeline=[{'captured_at_utc':r.get('captured_at_utc'),'stage':r.get('stage'),'line':r.get('line'),'odds':r.get('odds'),'sportsbook':r.get('sportsbook')} for r in rows]
        efficiency=max(0,min(100,50+clv*12+(oclv or 0)*120+min(15,max(0,len(rows)-1)*3)))
        records.append({'market_id':mid,'target_date':recommendation.get('target_date'),'player':recommendation.get('player'),'team':recommendation.get('team'),'game':recommendation.get('game'),'market_type':recommendation.get('market_type'),'stat':recommendation.get('stat'),'side':side,'sportsbook':recommendation.get('sportsbook'),'model_version':recommendation.get('model_version'),'confidence':recommendation.get('confidence'),'opening_line':open_line,'recommendation_line':rec_line,'closing_line':close_line,'opening_odds':opening.get('odds'),'recommendation_odds':recommendation.get('odds'),'closing_odds':closing.get('odds'),'line_clv':round(clv,4),'odds_clv_probability':round(oclv,4) if oclv is not None else None,'beat_closing_line':clv>0,'movement_classification':classify_movement(side,open_line,rec_line,close_line,None),'market_efficiency_score':round(efficiency,1),'observations':len(rows),'timeline':timeline,'explanation_summary':recommendation.get('explanation_summary'),'actual':actual.get('actual'),'outcome':actual.get('outcome'),'profit_loss':actual.get('profit_loss')})
    clvs=[r['line_clv'] for r in records];odds=[r['odds_clv_probability'] for r in records if r['odds_clv_probability'] is not None]
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'tracked_markets':len(records),'average_line_clv':round(sum(clvs)/len(clvs),4) if clvs else None,'median_line_clv':round(statistics.median(clvs),4) if clvs else None,'positive_clv_rate':round(sum(x>0 for x in clvs)/len(clvs),4) if clvs else None,'beat_close_rate':round(sum(r['beat_closing_line'] for r in records)/len(records),4) if records else None,'average_odds_clv':round(sum(odds)/len(odds),4) if odds else None,'average_market_efficiency_score':round(sum(r['market_efficiency_score'] for r in records)/len(records),2) if records else None},'records':sorted(records,key=lambda r:(r['target_date'],r['market_efficiency_score']),reverse=True)[:100],'by_stat':aggregate(records,'stat'),'by_player':aggregate(records,'player'),'by_team':aggregate(records,'team'),'by_sportsbook':aggregate(records,'sportsbook'),'by_model_version':aggregate(records,'model_version'),'by_confidence_tier':aggregate([{**r,'confidence_tier':('90-100' if (num(r.get('confidence')) or 0)>=90 else '80-89' if (num(r.get('confidence')) or 0)>=80 else '70-79' if (num(r.get('confidence')) or 0)>=70 else 'Below 70')} for r in records],'confidence_tier'),'feedback':{'eligible':len(records)>=100,'minimum_sample':100,'recommendations':[f"Review {r['group']} market calibration: average CLV {r['average_line_clv']:+.2f}" for r in aggregate(records,'stat') if r.get('count',0)>=30 and r.get('average_line_clv') is not None and r['average_line_clv']<-.25][:10],'automatic_model_changes':False},'methodology':{'opening':'first immutable observation','recommendation':'first actionable BET/LEAN observation, otherwise opening','closing':'latest available pregame observation','line_clv':'side-normalized recommendation value minus closing value; positive is favorable','odds_clv':'closing implied probability minus recommendation implied probability','market_efficiency':'CLV, odds movement, and observation lead-time proxy','sportsbook_scanner':False}}
    for p in OUTS:dump(p,payload)
    print('Market Intelligence:',payload['summary']);return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('capture','analyze','all'));ap.add_argument('--date',default=str(date.today()));ap.add_argument('--stage',default='current');a=ap.parse_args()
    if a.mode in {'capture','all'}:print('capture',capture(a.date,a.stage))
    if a.mode in {'analyze','all'}:analyze(a.date)
if __name__=='__main__':main()
