"""Resolve remaining ALT archive mappings with matchup/team identity evidence.

Step 3 targets pending records left after adjacent-date repair. It scores candidate
player-game rows using archived matchup text, team/opponent identity, home/away
orientation, and nearby schedule dates. Only uniquely best matches above a strict
confidence threshold are applied; ambiguous cases remain untouched.
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
REPORTS=[Path('data/warehouse/wnba_alt_matchup_mapping_repair.json'),Path('data/dashboard/wnba_alt_matchup_mapping_repair.json')]

TEAM_ALIASES={
 'liberty':'new york liberty','aces':'las vegas aces','lynx':'minnesota lynx','tempo':'toronto tempo',
 'mercury':'phoenix mercury','storm':'seattle storm','dream':'atlanta dream','wings':'dallas wings',
 'mystics':'washington mystics','fever':'indiana fever','sky':'chicago sky','sparks':'los angeles sparks',
 'sun':'connecticut sun','valkyries':'golden state valkyries','fire':'portland fire',
}

def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().replace('’',"'").replace('vs.',' vs ').replace('@',' @ ').split())

def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

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

def canon_team(value:Any)->str:
    text=norm(value)
    for alias,full in TEAM_ALIASES.items():
        if text==alias or text.endswith(' '+alias) or (' '+alias+' ') in (' '+text+' '):return full
    return text

def parse_matchup(value:Any)->tuple[str,str,str|None]:
    text=norm(value)
    if ' @ ' in text:
        a,b=text.split(' @ ',1);return canon_team(a),canon_team(b),'away_home'
    if ' vs ' in text:
        a,b=text.split(' vs ',1);return canon_team(a),canon_team(b),'home_away'
    return '', '', None

def record_teams(r:dict[str,Any])->tuple[set[str],str|None,str|None]:
    team=canon_team(r.get('team') or r.get('team_name'))
    opp=canon_team(r.get('opponent') or r.get('opponent_name'))
    home=canon_team(r.get('home_team'))
    away=canon_team(r.get('away_team'))
    teams={x for x in (team,opp,home,away) if x}
    return teams,home or None,away or None

def date_distance(a:str,b:str)->int|None:
    try:return abs((datetime.fromisoformat(a[:10])-datetime.fromisoformat(b[:10])).days)
    except Exception:return None

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

def score_candidate(row:dict[str,Any],r:dict[str,Any])->tuple[int,list[str]]:
    score=0;reasons=[]
    target=str(row.get('date') or '')[:10];game_date=str(r.get('game_date') or '')[:10]
    dist=date_distance(target,game_date)
    if dist is not None:
        score += max(0,30-10*dist);reasons.append(f'date_distance={dist}')
    a,b,orientation=parse_matchup(row.get('game') or row.get('opponent'))
    archived={x for x in (a,b,canon_team(row.get('team'))) if x}
    teams,home,away=record_teams(r)
    overlap=len(archived & teams)
    if overlap:
        score+=35*overlap;reasons.append(f'team_overlap={overlap}')
    if a and b and a in teams and b in teams:
        score+=35;reasons.append('both_matchup_teams')
    if orientation=='away_home' and away==a and home==b:
        score+=15;reasons.append('orientation_match')
    if orientation=='home_away' and home==a and away==b:
        score+=15;reasons.append('orientation_match')
    if canon_team(row.get('team')) and canon_team(row.get('team'))==canon_team(r.get('team') or r.get('team_name')):
        score+=15;reasons.append('player_team_match')
    return score,reasons

def main()->None:
    rows=read_jsonl(ARCHIVE);logs=load(LOGS,{'records':[]})
    by_player:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in logs.get('records',[]):
        if isinstance(r,dict) and r.get('player') and r.get('game_date'):by_player[norm(r['player'])].append(r)
    repaired=graded=ambiguous=low_conf=no_stat=unresolved=0;details=[]
    now=datetime.now(timezone.utc).isoformat()
    for row in rows:
        if str(row.get('outcome') or 'PENDING').upper()!='PENDING':continue
        player=norm(row.get('player'));target=str(row.get('date') or '')[:10]
        pool=[]
        for r in by_player.get(player,[]):
            dist=date_distance(target,str(r.get('game_date') or '')[:10])
            if dist is not None and dist<=3:
                score,reasons=score_candidate(row,r);pool.append((score,r,reasons))
        if not pool:
            unresolved+=1;continue
        pool.sort(key=lambda x:x[0],reverse=True)
        top=pool[0];second=pool[1] if len(pool)>1 else None
        if top[0] < 70:
            low_conf+=1;continue
        if second is not None and top[0]-second[0] < 20:
            ambiguous+=1;continue
        chosen=top[1]
        actual=stat_value(chosen,str(row.get('stat') or ''))
        if actual is None:
            no_stat+=1;continue
        out=result(str(row.get('side') or ''),actual,num(row.get('alt_line')))
        if out=='PENDING':
            no_stat+=1;continue
        old_date=target;new_date=str(chosen.get('game_date') or '')[:10]
        row['archive_date_original']=row.get('archive_date_original') or row.get('date')
        row['date']=new_date;row['actual']=actual;row['outcome']=out;row['profit_loss']=profit(out,row.get('best_odds'))
        row['graded_at_utc']=now;row['actual_source']='player_game_log_warehouse';row['grading_reason']=None
        row['game_mapping_repaired']=True;row['game_mapping_method']='matchup_team_identity'
        row['game_mapping_score']=top[0];row['game_mapping_evidence']=top[2];row['game_mapping_repaired_at_utc']=now
        repaired+=1;graded+=1
        details.append({'candidate_id':row.get('candidate_id'),'player':row.get('player'),'old_date':old_date,'new_date':new_date,'score':top[0],'evidence':top[2],'actual':actual,'outcome':out})
    write_jsonl(ARCHIVE,rows)
    report={'generated_at_utc':now,'summary':{'pending_examined':sum(str(r.get('outcome') or '').upper()=='PENDING' for r in rows)+graded,'mappings_repaired':repaired,'newly_graded':graded,'ambiguous_matches':ambiguous,'low_confidence':low_conf,'matched_record_missing_stat':no_stat,'unresolved':unresolved},'records':details}
    for p in REPORTS:
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))

if __name__=='__main__':main()
