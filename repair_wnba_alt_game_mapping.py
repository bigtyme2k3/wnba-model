"""Repair ALT archive game-date mappings and grade newly matched records.

Step 2 targets archive rows classified as game_mapping_failed because the player
exists in the actuals warehouse on a nearby date. It resolves one-day date drift
using archived matchup text when possible, otherwise a unique adjacent-date
player record, then grades the record with the verified stat.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE=Path('data/history/wnba_alt_streak_history.jsonl')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
REPORTS=[Path('data/warehouse/wnba_alt_game_mapping_repair.json'),Path('data/dashboard/wnba_alt_game_mapping_repair.json')]


def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def read_jsonl(path:Path)->list[dict[str,Any]]:
    out=[]
    if path.exists():
        for line in path.open(encoding='utf-8'):
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out

def write_jsonl(path:Path,rows:list[dict[str,Any]])->None:
    with path.open('w',encoding='utf-8') as h:
        for row in rows:h.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')

def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def stat_value(record:dict[str,Any],stat:str)->float|None:
    key=str(stat or '').upper().replace('THREES','3PM').replace(' ','_')
    s=record.get('scoring',{}) if isinstance(record.get('scoring'),dict) else {}
    b=record.get('boxscore',{}) if isinstance(record.get('boxscore'),dict) else {}
    f=record.get('fouls',{}) if isinstance(record.get('fouls'),dict) else {}
    d=record.get('derived',{}) if isinstance(record.get('derived'),dict) else {}
    values={'PTS':s.get('total_pts'),'Q1_PTS':s.get('q1_pts'),'Q2_PTS':s.get('q2_pts'),'Q3_PTS':s.get('q3_pts'),'Q4_PTS':s.get('q4_pts'),'1H_PTS':s.get('first_half_pts'),'2H_PTS':s.get('second_half_pts'),'FTM':s.get('ftm'),'FTA':s.get('fta'),'FT_PTS':s.get('free_throw_points'),'3PM':s.get('three_pm'),'REB':b.get('reb'),'OREB':b.get('oreb'),'DREB':b.get('dreb'),'AST':b.get('ast'),'STL':b.get('stl'),'BLK':b.get('blk'),'TOV':b.get('tov'),'PF':f.get('total_committed'),'SHOOTING_FOULS':f.get('shooting'),'OFFENSIVE_FOULS':f.get('offensive'),'TECHNICAL_FOULS':f.get('technical'),'FLAGRANT_FOULS':f.get('flagrant'),'PRA':d.get('pra'),'PR':d.get('pr'),'PA':d.get('pa'),'RA':d.get('ra')}
    return num(values.get(key))
def result(side:str,actual:float|None,line:float|None)->str:
    if actual is None or line is None:return 'PENDING'
    if actual==line:return 'PUSH'
    if str(side).upper()=='OVER':return 'WIN' if actual>line else 'LOSS'
    if str(side).upper()=='UNDER':return 'WIN' if actual<line else 'LOSS'
    return 'VOID'
def profit(outcome:str,odds:Any)->float|None:
    p=num(odds)
    if outcome in {'PUSH','VOID'}:return 0.0
    if outcome=='LOSS':return -1.0
    if outcome!='WIN' or p in (None,0):return None
    return round(100/abs(p),4) if p<0 else round(p/100,4)
def matchup_tokens(value:Any)->set[str]:
    text=norm(value).replace('@',' ').replace('vs.',' ').replace('vs',' ')
    stop={'new','york','los','angeles','las','vegas','connecticut','washington','indiana','chicago','phoenix','seattle','atlanta','dallas','minnesota','golden','state','toronto','portland'}
    return {x for x in text.split() if len(x)>3 and x not in stop}
def record_text(r:dict[str,Any])->str:
    vals=[r.get(k) for k in ('game','matchup','opponent','team','team_name','opponent_name','home_team','away_team')]
    return norm(' '.join(str(v or '') for v in vals))
def date_distance(a:str,b:str)->int|None:
    try:return abs((datetime.fromisoformat(a[:10])-datetime.fromisoformat(b[:10])).days)
    except Exception:return None

def main()->None:
    rows=read_jsonl(ARCHIVE);logs=load(LOGS,{'records':[]})
    by_player:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in logs.get('records',[]):
        if isinstance(r,dict) and r.get('player') and r.get('game_date'):by_player[norm(r['player'])].append(r)
    repaired=graded=ambiguous=no_stat=unresolved=0;details=[]
    now=datetime.now(timezone.utc).isoformat()
    for row in rows:
        if str(row.get('outcome') or 'PENDING').upper()!='PENDING':continue
        player=norm(row.get('player'));target=str(row.get('date') or '')[:10]
        candidates=[]
        for r in by_player.get(player,[]):
            dist=date_distance(target,str(r.get('game_date') or '')[:10])
            if dist is not None and dist<=1:candidates.append((dist,r))
        exact=[r for dist,r in candidates if dist==0]
        if exact:continue
        adjacent=[r for dist,r in candidates if dist==1]
        if not adjacent:
            unresolved+=1;continue
        archive_tokens=matchup_tokens(row.get('game') or row.get('opponent'))
        scored=[]
        for r in adjacent:
            txt=record_text(r)
            score=sum(1 for t in archive_tokens if t in txt)
            scored.append((score,r))
        scored.sort(key=lambda x:x[0],reverse=True)
        chosen=None;method=None
        if scored and scored[0][0]>0 and (len(scored)==1 or scored[0][0]>scored[1][0]):
            chosen=scored[0][1];method='adjacent_date_matchup'
        elif len(adjacent)==1:
            chosen=adjacent[0];method='unique_adjacent_date'
        else:
            ambiguous+=1;continue
        actual=stat_value(chosen,str(row.get('stat') or ''))
        if actual is None:
            no_stat+=1;continue
        out=result(str(row.get('side') or ''),actual,num(row.get('alt_line')))
        if out=='PENDING':
            no_stat+=1;continue
        old_date=target;new_date=str(chosen.get('game_date') or '')[:10]
        row['archive_date_original']=row.get('date')
        row['date']=new_date
        row['actual']=actual;row['outcome']=out;row['profit_loss']=profit(out,row.get('best_odds'))
        row['graded_at_utc']=now;row['actual_source']='player_game_log_warehouse'
        row['grading_reason']=None;row['game_mapping_repaired']=True
        row['game_mapping_method']=method;row['game_mapping_repaired_at_utc']=now
        repaired+=1;graded+=1
        details.append({'candidate_id':row.get('candidate_id'),'player':row.get('player'),'old_date':old_date,'new_date':new_date,'method':method,'actual':actual,'outcome':out})
    write_jsonl(ARCHIVE,rows)
    report={'generated_at_utc':now,'summary':{'pending_examined':sum(str(r.get('outcome') or '').upper()=='PENDING' for r in rows)+graded,'mappings_repaired':repaired,'newly_graded':graded,'ambiguous_adjacent_matches':ambiguous,'matched_record_missing_stat':no_stat,'unresolved':unresolved},'records':details}
    for p in REPORTS:
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))

if __name__=='__main__':main()
