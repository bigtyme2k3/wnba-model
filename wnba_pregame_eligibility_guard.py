"""Lock live/final games out of actionable WNBA recommendations and injury rankings."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard'); WH=Path('data/warehouse')
MASTER_PATHS=[DASH/'wnba_master.json',Path('data/master/wnba_master.json')]
INJURY_PATHS=[DASH/'wnba_injury_intelligence.json',WH/'wnba_injury_intelligence.json']
DECISION_PATHS=[
 DASH/'wnba_decision_engine_final.json',WH/'wnba_decision_engine_final.json',
 DASH/'wnba_portfolio_optimizer_v2.json',WH/'wnba_portfolio_optimizer_v2.json',
 DASH/'wnba_risk_allocation.json',WH/'wnba_risk_allocation.json',
 DASH/'wnba_portfolio_dashboard.json',WH/'wnba_portfolio_dashboard.json',
]
LIVE_WORDS={'live','in progress','in_progress','halftime','end period','q1','q2','q3','q4','ot'}
FINAL_WORDS={'final','completed','complete','closed','postgame','ended'}
PREGAME_WORDS={'pregame','scheduled','not started','not_started','upcoming'}

def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def dump(path:Path,data:Any):
    path.parent.mkdir(parents=True,exist_ok=True)
    json.dump(data,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)

def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().replace('_',' ').split())

def parse_time(v:Any):
    if not v:return None
    s=str(v).strip().replace('Z','+00:00')
    try:
        dt=datetime.fromisoformat(s)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:return None

def game_state(game:dict,now:datetime)->str:
    raw=norm(game.get('status') or game.get('game_status') or game.get('state') or game.get('status_type') or game.get('event_status'))
    if any(x in raw for x in FINAL_WORDS):return 'FINAL'
    if any(x in raw for x in LIVE_WORDS):return 'LIVE'
    if any(x in raw for x in PREGAME_WORDS):return 'PREGAME'
    start=parse_time(game.get('commence_time') or game.get('start_time') or game.get('game_time') or game.get('scheduled') or game.get('date'))
    if start:
        # Hard lock at scheduled tip. Never reopen without an explicit pregame status.
        if now>=start+timedelta(hours=4):return 'FINAL'
        if now>=start:return 'LIVE'
    return 'PREGAME'

def game_teams(game:dict)->set[str]:
    return {str(game.get(k)).strip() for k in ('home_team','away_team','home','away') if game.get(k)}

def mark_rows(rows:list,locked_teams:set[str],locked_games:set[str]):
    out=[]
    for raw in rows or []:
        row=dict(raw)
        team=str(row.get('team') or row.get('team_name') or '').strip()
        opponent=str(row.get('opponent') or '').strip()
        game_id=str(row.get('game_id') or row.get('event_id') or row.get('matchup_id') or '')
        matchup=norm(row.get('matchup') or row.get('game') or '')
        locked=team in locked_teams or opponent in locked_teams or game_id in locked_games or any(norm(t) in matchup for t in locked_teams)
        if locked:
            row['pregame_eligible']=False
            row['game_locked']=True
            row['game_state']='LIVE_OR_FINAL'
            row['final_action']='PASS';row['recommendation']='PASS'
            row['eligible']=False;row['eligible_for_bet']=False
            row['blocked_reason']='Game already started — pregame market locked'
        else:
            row.setdefault('pregame_eligible',True)
        out.append(row)
    return out

def main():
    now=datetime.now(timezone.utc)
    master=next((load(p,{}) for p in MASTER_PATHS if p.exists()),{})
    games=master.get('games',[]) or master.get('today_games',[]) or []
    locked_teams=set();pregame_teams=set();locked_games=set();states=[]
    for g in games:
        state=game_state(g,now);teams=game_teams(g);gid=str(g.get('game_id') or g.get('event_id') or g.get('id') or '')
        states.append({'game_id':gid,'teams':sorted(teams),'state':state})
        g['pregame_eligible']=state=='PREGAME';g['game_state']=state
        if state=='PREGAME':pregame_teams|=teams
        else:
            locked_teams|=teams
            if gid:locked_games.add(gid)
    for path in MASTER_PATHS:
        data=load(path,None)
        if data is None:continue
        rows=data.get('props',[]) or []
        data['props']=mark_rows(rows,locked_teams,locked_games)
        for key in ('best_bets','top_plays','recommendations','portfolio'):
            if isinstance(data.get(key),list):data[key]=mark_rows(data[key],locked_teams,locked_games)
        data['pregame_guard']={'generated_at_utc':now.isoformat(),'pregame_teams':sorted(pregame_teams),'locked_teams':sorted(locked_teams),'games':states}
        dump(path,data)
    for path in INJURY_PATHS:
        report=load(path,None)
        if report is None:continue
        adjusted=[]
        for raw in report.get('adjustments',[]) or []:
            row=dict(raw);team=str(row.get('team') or '').strip();locked=team in locked_teams
            row['pregame_eligible']=not locked;row['game_locked']=locked
            if locked:
                row['headline_eligible']=False
                row['detail']=(row.get('detail') or '')+'; game live/final — pregame opportunity locked'
            adjusted.append(row)
        report['adjustments']=adjusted
        report['pregame_guard']={'generated_at_utc':now.isoformat(),'pregame_teams':sorted(pregame_teams),'locked_teams':sorted(locked_teams),'games':states}
        report.setdefault('summary',{})['pregame_eligible_beneficiaries']=sum(1 for r in adjusted if r.get('headline_eligible') and r.get('pregame_eligible'))
        report['summary']['locked_live_or_final_teams']=len(locked_teams)
        dump(path,report)
    for path in DECISION_PATHS:
        data=load(path,None)
        if data is None:continue
        if isinstance(data,list):data=mark_rows(data,locked_teams,locked_games)
        elif isinstance(data,dict):
            for key in ('rows','decisions','top_decisions','qualified_bets','final_decisions','recommended_card','candidates','bets','portfolio','allocations'):
                if isinstance(data.get(key),list):data[key]=mark_rows(data[key],locked_teams,locked_games)
            data['pregame_guard']={'generated_at_utc':now.isoformat(),'locked_teams':sorted(locked_teams)}
        dump(path,data)
    print(json.dumps({'pregame_teams':sorted(pregame_teams),'locked_teams':sorted(locked_teams),'games':states},indent=2))

if __name__=='__main__':main()
