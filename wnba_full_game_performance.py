"""Freeze, grade, and diagnose Full-Game Simulation v2.

Game projections and direct cross-player pairs are snapshotted before tipoff.
Final scores come from ESPN score history; player-leg outcomes come from the
verified Player Game Log Warehouse. No calibration parameter is changed here.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

FULL=Path('data/dashboard/wnba_full_game_simulation_v2.json')
GAME_HISTORY=Path('data/history/wnba_full_game_projection_history.jsonl')
PAIR_HISTORY=Path('data/history/wnba_full_game_pair_history.jsonl')
SCORES=Path('data/raw/scores_historical.csv')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
OUTS=[Path('data/warehouse/wnba_full_game_performance.json'),Path('data/dashboard/wnba_full_game_performance.json')]

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def read_jsonl(p:Path)->list[dict[str,Any]]:
    out=[]
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict):out.append(r)
            except Exception:pass
    return out
def write_jsonl(p:Path,rows:list[dict[str,Any]])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def teams(game:str)->tuple[str,str]:
    parts=[x.strip() for x in str(game or '').replace(' vs ',' @ ').split(' @ ') if x.strip()]
    return (parts[0],parts[1]) if len(parts)>=2 else ('','')
def actual_stat(row:dict[str,Any],stat:str)->float|None:
    s=row.get('scoring',{}) if isinstance(row.get('scoring'),dict) else {};b=row.get('boxscore',{}) if isinstance(row.get('boxscore'),dict) else {}
    pts=num(s.get('total_pts'));reb=num(b.get('reb'));ast=num(b.get('ast'))
    values={'PTS':pts,'REB':reb,'AST':ast,'3PM':num(s.get('three_pm')),'STL':num(b.get('stl')),'BLK':num(b.get('blk')),'TOV':num(b.get('tov'))}
    if None not in (pts,reb,ast):values.update({'PRA':pts+reb+ast,'PR':pts+reb,'PA':pts+ast,'RA':reb+ast})
    return values.get(stat)
def snapshot(target:str)->dict[str,int]:
    payload=load(FULL,{'games':[]});games=read_jsonl(GAME_HISTORY);pairs=read_jsonl(PAIR_HISTORY);gseen={r.get('snapshot_id') for r in games};pseen={r.get('snapshot_id') for r in pairs};ga=pa=0;now=datetime.now(timezone.utc).isoformat()
    for g in payload.get('games',[]):
        gid=f"{target}|{norm(g.get('game'))}"
        if gid not in gseen:
            s=g.get('score_distribution',{});games.append({'snapshot_id':gid,'date':target,'captured_at_utc':now,'game':g.get('game'),'away_team':g.get('away_team'),'home_team':g.get('home_team'),'away_mean':s.get('away_mean'),'home_mean':s.get('home_mean'),'total_mean':s.get('total_mean'),'margin_mean':s.get('margin_mean'),'total_p10':s.get('total_p10'),'total_p90':s.get('total_p90'),'margin_p10':s.get('margin_p10'),'margin_p90':s.get('margin_p90'),'overtime_probability':s.get('overtime_probability'),'actual_away':None,'actual_home':None,'status':'PENDING'});gseen.add(gid);ga+=1
        for i,pair in enumerate(g.get('direct_cross_player_pairs',[])):
            pid=f"{gid}|pair|{i}|{json.dumps(pair.get('legs',[]),sort_keys=True)}"
            if pid in pseen:continue
            pairs.append({'snapshot_id':pid,'date':target,'captured_at_utc':now,'game':g.get('game'),'legs':pair.get('legs',[]),'predicted_probability':pair.get('joint_probability'),'correlation':pair.get('correlation'),'calculation_method':'DIRECT_FULL_GAME_SIMULATION','actual_hit':None,'status':'PENDING'});pseen.add(pid);pa+=1
    write_jsonl(GAME_HISTORY,games);write_jsonl(PAIR_HISTORY,pairs);return {'games_added':ga,'pairs_added':pa}
def score_index()->dict[tuple[str,str,str],dict[str,Any]]:
    out={}
    if not SCORES.exists():return out
    with SCORES.open(encoding='utf-8-sig',newline='') as h:
        for r in csv.DictReader(h):
            if str(r.get('is_final')).lower() not in {'true','1'} and 'FINAL' not in str(r.get('status')).upper():continue
            out[(str(r.get('game_date'))[:10],norm(r.get('away_team')),norm(r.get('home_team')))]=r
    return out
def grade()->dict[str,int]:
    games=read_jsonl(GAME_HISTORY);pairs=read_jsonl(PAIR_HISTORY);scores=score_index();logs=load(LOGS,{'records':[]}).get('records',[]);pidx={(str(r.get('game_date'))[:10],norm(r.get('player'))):r for r in logs};gg=pg=0
    for r in games:
        if r.get('status')!='PENDING':continue
        away,home=teams(r.get('game'));score=scores.get((str(r.get('date')),norm(away),norm(home)))
        if not score:continue
        ah=num(score.get('away_score'));hh=num(score.get('home_score'))
        if ah is None or hh is None:continue
        total=ah+hh;margin=hh-ah;r.update({'actual_away':ah,'actual_home':hh,'actual_total':total,'actual_margin':margin,'total_error':round((num(r.get('total_mean')) or 0)-total,4),'total_absolute_error':round(abs((num(r.get('total_mean')) or 0)-total),4),'margin_error':round((num(r.get('margin_mean')) or 0)-margin,4),'margin_absolute_error':round(abs((num(r.get('margin_mean')) or 0)-margin),4),'total_inside_p10_p90':bool((num(r.get('total_p10')) or -1e9)<=total<=(num(r.get('total_p90')) or 1e9)),'margin_inside_p10_p90':bool((num(r.get('margin_p10')) or -1e9)<=margin<=(num(r.get('margin_p90')) or 1e9)),'actual_overtime':bool(total>200 or ah==hh),'actual_blowout':abs(margin)>=15,'status':'GRADED','actual_source':'scores_historical.csv'});gg+=1
    for r in pairs:
        if r.get('status')!='PENDING':continue
        hits=[];ready=True
        for leg in r.get('legs',[]):
            log=pidx.get((str(r.get('date')),norm(leg.get('player'))));actual=actual_stat(log or {},str(leg.get('stat')))
            line=num(leg.get('line'))
            if actual is None or line is None:ready=False;break
            hits.append(actual>line if str(leg.get('side')).upper()=='OVER' else actual<line)
        if not ready:continue
        r.update({'actual_hit':bool(all(hits)),'status':'GRADED','actual_source':'player_game_log_warehouse'});pg+=1
    write_jsonl(GAME_HISTORY,games);write_jsonl(PAIR_HISTORY,pairs);return {'games_graded':gg,'pairs_graded':pg}
def mean(rows:list[dict[str,Any]],field:str)->float|None:
    vals=[num(r.get(field)) for r in rows];vals=[x for x in vals if x is not None];return sum(vals)/len(vals) if vals else None
def pair_calibration(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    bands=[(.10,.20),(.20,.30),(.30,.40),(.40,.50),(.50,1.01)];out=[]
    for lo,hi in bands:
        s=[r for r in rows if r.get('status')=='GRADED' and num(r.get('predicted_probability')) is not None and lo<=num(r.get('predicted_probability'))<hi]
        if not s:continue
        pred=sum(num(r.get('predicted_probability')) or 0 for r in s)/len(s);actual=sum(bool(r.get('actual_hit')) for r in s)/len(s);out.append({'band':f'{int(lo*100)}-{int(min(hi,1)*100)}%','count':len(s),'predicted':round(pred,4),'actual':round(actual,4),'calibration_error':round(actual-pred,4)})
    return out
def analyze(target:str)->dict[str,Any]:
    games=[r for r in read_jsonl(GAME_HISTORY) if r.get('status')=='GRADED'];pairs=[r for r in read_jsonl(PAIR_HISTORY) if r.get('status')=='GRADED'];ot_pred=mean(games,'overtime_probability');ot_actual=sum(bool(r.get('actual_overtime')) for r in games)/len(games) if games else None
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'games_graded':len(games),'total_mae':round(mean(games,'total_absolute_error'),4) if games else None,'total_bias':round(mean(games,'total_error'),4) if games else None,'margin_mae':round(mean(games,'margin_absolute_error'),4) if games else None,'margin_bias':round(mean(games,'margin_error'),4) if games else None,'total_p10_p90_coverage':round(sum(bool(r.get('total_inside_p10_p90')) for r in games)/len(games),4) if games else None,'margin_p10_p90_coverage':round(sum(bool(r.get('margin_inside_p10_p90')) for r in games)/len(games),4) if games else None,'overtime_predicted':round(ot_pred,4) if ot_pred is not None else None,'overtime_actual':round(ot_actual,4) if ot_actual is not None else None,'blowout_rate':round(sum(bool(r.get('actual_blowout')) for r in games)/len(games),4) if games else None,'direct_pairs_graded':len(pairs),'direct_pair_hit_rate':round(sum(bool(r.get('actual_hit')) for r in pairs)/len(pairs),4) if pairs else None},'pair_probability_calibration':pair_calibration(pairs),'calibration_status':{'pace_variance':'ELIGIBLE' if len(games)>=100 else 'LOCKED','efficiency_variance':'ELIGIBLE' if len(games)>=100 else 'LOCKED','overtime_probability':'ELIGIBLE' if len(games)>=200 else 'LOCKED','cross_player_correlation':'ELIGIBLE' if len(pairs)>=200 else 'LOCKED'},'thresholds':{'game_environment_review':100,'overtime_review':200,'direct_pair_correlation_review':200},'policy':{'automatic_parameter_changes':False,'game_actual_source':'scores_historical.csv','pair_actual_source':'player_game_log_warehouse','pregame_snapshots_immutable':True}}
    for p in OUTS:dump(p,payload)
    return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('snapshot','grade','analyze','all'));ap.add_argument('--date',default=str(date.today()));a=ap.parse_args()
    if a.mode in {'snapshot','all'}:print('snapshot',snapshot(a.date))
    if a.mode in {'grade','all'}:print('grade',grade())
    if a.mode in {'analyze','all'}:print('analyze',analyze(a.date)['summary'])
if __name__=='__main__':main()
