"""Sprint 20 Step 4: repair remaining ALT archive mappings with schedule metadata.

Uses official/normalized schedule rows, team aliases, matchup orientation, player
team/opponent fields, and snapshot timing. Only high-confidence unique matches are
graded; ambiguous records remain untouched and are reported.
"""
from __future__ import annotations

import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE=Path('data/history/wnba_alt_streak_history.jsonl')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
SCHEDULE_SOURCES=[Path('data/dashboard/wnba_live_games.json'),Path('data/wnba/scores.json')]
REPORTS=[Path('data/warehouse/wnba_alt_schedule_mapping_repair.json'),Path('data/dashboard/wnba_alt_schedule_mapping_repair.json')]

ALIASES={
 'ny liberty':'new york liberty','new york':'new york liberty','liberty':'new york liberty',
 'la sparks':'los angeles sparks','los angeles':'los angeles sparks','sparks':'los angeles sparks',
 'lv aces':'las vegas aces','las vegas':'las vegas aces','aces':'las vegas aces',
 'gs valkyries':'golden state valkyries','golden state':'golden state valkyries','valkyries':'golden state valkyries',
 'dc mystics':'washington mystics','washington':'washington mystics','mystics':'washington mystics',
 'conn sun':'connecticut sun','connecticut':'connecticut sun','sun':'connecticut sun',
 'minnesota':'minnesota lynx','lynx':'minnesota lynx','atlanta':'atlanta dream','dream':'atlanta dream',
 'chicago':'chicago sky','sky':'chicago sky','seattle':'seattle storm','storm':'seattle storm',
 'dallas':'dallas wings','wings':'dallas wings','phoenix':'phoenix mercury','mercury':'phoenix mercury',
 'indiana':'indiana fever','fever':'indiana fever','portland':'portland fire','fire':'portland fire',
 'toronto':'toronto tempo','tempo':'toronto tempo'
}

def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").replace('.','').split())
def team(v:Any)->str:
    n=norm(v)
    return ALIASES.get(n,n)
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
                r=json.loads(line)
                if isinstance(r,dict):out.append(r)
            except Exception:pass
    return out
def write_jsonl(path:Path,rows:list[dict[str,Any]])->None:
    with path.open('w',encoding='utf-8') as h:
        for r in rows:h.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')
def stat_value(r:dict[str,Any],stat:str)->float|None:
    k=str(stat or '').upper().replace('THREES','3PM').replace(' ','_')
    s=r.get('scoring',{}) if isinstance(r.get('scoring'),dict) else {};b=r.get('boxscore',{}) if isinstance(r.get('boxscore'),dict) else {};d=r.get('derived',{}) if isinstance(r.get('derived'),dict) else {};f=r.get('fouls',{}) if isinstance(r.get('fouls'),dict) else {}
    vals={'PTS':s.get('total_pts'),'3PM':s.get('three_pm'),'REB':b.get('reb'),'AST':b.get('ast'),'STL':b.get('stl'),'BLK':b.get('blk'),'TOV':b.get('tov'),'OREB':b.get('oreb'),'DREB':b.get('dreb'),'PRA':d.get('pra'),'PR':d.get('pr'),'PA':d.get('pa'),'RA':d.get('ra'),'PF':f.get('total_committed')}
    return num(vals.get(k))
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
def parse_matchup(v:Any)->tuple[str,str]:
    t=norm(v).replace(' vs. ',' @ ').replace(' vs ',' @ ')
    if '@' not in t:return ('','')
    a,h=[team(x) for x in t.split('@',1)]
    return a,h
def iso_date(v:Any)->str:return str(v or '')[:10]
def date_diff(a:str,b:str)->int:
    try:return abs((datetime.fromisoformat(a)-datetime.fromisoformat(b)).days)
    except Exception:return 99

def schedule_rows()->list[dict[str,Any]]:
    out=[]
    for p in SCHEDULE_SOURCES:
        data=load(p,{})
        rows=data.get('games',[]) if isinstance(data,dict) else data if isinstance(data,list) else []
        for g in rows:
            if not isinstance(g,dict):continue
            away=team(g.get('away_team'));home=team(g.get('home_team'))
            if not (away and home):
                away,home=parse_matchup(g.get('game') or g.get('matchup'))
            if away and home:out.append({'game_id':g.get('game_id') or g.get('id'),'game_date':iso_date(g.get('game_date') or g.get('date') or g.get('start_time')),'away_team':away,'home_team':home,'start_time':g.get('start_time'),'status':g.get('status')})
    unique={}
    for g in out:unique[(g['game_date'],g['away_team'],g['home_team'])]=g
    return list(unique.values())

def main()->None:
    rows=read_jsonl(ARCHIVE);logs=load(LOGS,{'records':[]});games=schedule_rows()
    by_player=defaultdict(list)
    for r in logs.get('records',[]):
        if isinstance(r,dict) and r.get('player') and r.get('game_date'):by_player[norm(r['player'])].append(r)
    repaired=graded=ambiguous=low_conf=no_schedule=no_stat=0;details=[];now=datetime.now(timezone.utc).isoformat()
    for row in rows:
        if str(row.get('outcome') or 'PENDING').upper()!='PENDING':continue
        player=norm(row.get('player'));target=iso_date(row.get('date'));away,home=parse_matchup(row.get('game') or row.get('opponent'))
        schedule_candidates=[]
        for g in games:
            dd=date_diff(target,g['game_date'])
            if dd<=3:
                score=0
                if away and home and g['away_team']==away and g['home_team']==home:score+=70
                elif away and home and {g['away_team'],g['home_team']}=={away,home}:score+=55
                if dd==0:score+=20
                elif dd==1:score+=12
                elif dd==2:score+=6
                if score:schedule_candidates.append((score,g))
        schedule_candidates.sort(key=lambda x:x[0],reverse=True)
        if not schedule_candidates:
            no_schedule+=1;continue
        top=schedule_candidates[0];second=schedule_candidates[1][0] if len(schedule_candidates)>1 else -1
        if top[0]<70:
            low_conf+=1;continue
        if second>=0 and top[0]-second<15:
            ambiguous+=1;continue
        game=top[1]
        actual_candidates=[]
        for r in by_player.get(player,[]):
            if iso_date(r.get('game_date'))!=game['game_date']:continue
            rt=team(r.get('team') or r.get('team_name'));ro=team(r.get('opponent') or r.get('opponent_name'))
            evidence=0
            if rt in {game['away_team'],game['home_team']}:evidence+=40
            if ro in {game['away_team'],game['home_team']} and ro!=rt:evidence+=35
            actual_candidates.append((evidence,r))
        actual_candidates.sort(key=lambda x:x[0],reverse=True)
        if not actual_candidates or actual_candidates[0][0]<40:
            low_conf+=1;continue
        if len(actual_candidates)>1 and actual_candidates[0][0]==actual_candidates[1][0]:
            ambiguous+=1;continue
        chosen=actual_candidates[0][1];actual=stat_value(chosen,str(row.get('stat') or ''))
        if actual is None:
            no_stat+=1;continue
        out=result(str(row.get('side') or ''),actual,num(row.get('alt_line')))
        if out=='PENDING':no_stat+=1;continue
        old=row.get('date');row['archive_date_original']=row.get('archive_date_original') or old;row['date']=game['game_date'];row['actual']=actual;row['outcome']=out;row['profit_loss']=profit(out,row.get('best_odds'));row['graded_at_utc']=now;row['actual_source']='player_game_log_warehouse';row['grading_reason']=None;row['game_mapping_repaired']=True;row['game_mapping_method']='schedule_team_identity';row['game_id']=game.get('game_id');row['game_mapping_repaired_at_utc']=now
        repaired+=1;graded+=1;details.append({'candidate_id':row.get('candidate_id'),'player':row.get('player'),'old_date':old,'new_date':game['game_date'],'game_id':game.get('game_id'),'score':top[0],'actual':actual,'outcome':out})
    write_jsonl(ARCHIVE,rows)
    report={'generated_at_utc':now,'summary':{'pending_examined':sum(str(r.get('outcome') or '').upper()=='PENDING' for r in rows)+graded,'mappings_repaired':repaired,'newly_graded':graded,'ambiguous':ambiguous,'low_confidence':low_conf,'no_schedule_match':no_schedule,'matched_record_missing_stat':no_stat,'remaining_pending':sum(str(r.get('outcome') or '').upper()=='PENDING' for r in rows)},'records':details}
    for p in REPORTS:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))
if __name__=='__main__':main()
