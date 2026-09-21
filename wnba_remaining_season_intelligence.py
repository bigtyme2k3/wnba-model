from __future__ import annotations

import json, math, os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

OUT=Path('data/dashboard/wnba_remaining_season_intelligence.json')
MASTER=Path('data/dashboard/wnba_master.json')
COORDS={
'ATL':(33.757,-84.396),'CHI':(41.880,-87.674),'CONN':(41.383,-72.102),'DAL':(32.790,-96.810),
'GS':(37.750,-122.203),'IND':(39.764,-86.156),'LA':(34.043,-118.267),'LV':(36.090,-115.178),
'MIN':(44.979,-93.276),'NY':(40.682,-73.975),'PHX':(33.446,-112.071),'POR':(45.531,-122.666),
'SEA':(47.622,-122.354),'TOR':(43.643,-79.379),'WAS':(38.898,-77.021)}
ALIASES={'WSH':'WAS','NYL':'NY','LVA':'LV','LAS':'LA','CON':'CONN','GSV':'GS'}
NAME_TO_ABBR={
'Atlanta Dream':'ATL','Chicago Sky':'CHI','Connecticut Sun':'CONN','Dallas Wings':'DAL',
'Golden State Valkyries':'GS','Indiana Fever':'IND','Los Angeles Sparks':'LA','Las Vegas Aces':'LV',
'Minnesota Lynx':'MIN','New York Liberty':'NY','Phoenix Mercury':'PHX','Portland Fire':'POR',
'Seattle Storm':'SEA','Toronto Tempo':'TOR','Washington Mystics':'WAS'
}

def get_json(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 wnba-model/1.1','Accept':'application/json'})
    with urlopen(req,timeout=30) as r:return json.load(r)

def norm(x): return ALIASES.get(x,x)
def target_date():
    raw=os.environ.get('TARGET') or os.environ.get('WNBA_TARGET_DATE')
    try:return date.fromisoformat(str(raw)[:10]) if raw else datetime.now(timezone.utc).date()
    except Exception:return datetime.now(timezone.utc).date()

def hav(a,b):
    if a not in COORDS or b not in COORDS:return 0.0
    p1,p2=COORDS[a],COORDS[b]; r=3958.8
    x1,x2=map(math.radians,(p1[0],p2[0])); dlat=math.radians(p2[0]-p1[0]);dlon=math.radians(p2[1]-p1[1])
    q=math.sin(dlat/2)**2+math.cos(x1)*math.cos(x2)*math.sin(dlon/2)**2
    return 2*r*math.asin(math.sqrt(q))

def parse_events(raw,cutoff):
    games=[]
    seen=set()
    for e in raw.get('events',[]):
        try:dt=datetime.fromisoformat(e['date'].replace('Z','+00:00'))
        except Exception:continue
        if dt.date() < cutoff:continue
        comp=(e.get('competitions') or [{}])[0]; teams=comp.get('competitors') or []
        home=next((t for t in teams if t.get('homeAway')=='home'),None); away=next((t for t in teams if t.get('homeAway')=='away'),None)
        if not home or not away:continue
        h=norm(home.get('team',{}).get('abbreviation',''));a=norm(away.get('team',{}).get('abbreviation',''))
        k=(str(e.get('id') or ''),dt.isoformat(),h,a)
        if k in seen:continue
        seen.add(k)
        games.append({'event_id':e.get('id'),'date_utc':dt.isoformat(),'home':h,'away':a,'name':e.get('name',f'{a} at {h}'),'venue':comp.get('venue',{}).get('fullName','')})
    return sorted(games,key=lambda x:x['date_utc'])

def canonical_fallback(cutoff):
    try:payload=json.loads(MASTER.read_text(encoding='utf-8'))
    except Exception:return []
    games=[]
    for g in payload.get('games') or []:
        gd=str(g.get('game_date') or '')[:10]
        try:d=date.fromisoformat(gd)
        except Exception:continue
        if d < cutoff or 'FINAL' in str(g.get('status') or '').upper():continue
        h=NAME_TO_ABBR.get(str(g.get('home_team') or ''),str(g.get('home_team') or ''))
        a=NAME_TO_ABBR.get(str(g.get('away_team') or ''),str(g.get('away_team') or ''))
        stamp=str(g.get('start_time') or '')
        if not stamp: stamp=f'{gd}T12:00:00+00:00'
        elif stamp.endswith('Z'): stamp=stamp[:-1]+'+00:00'
        games.append({'event_id':g.get('game_id'),'date_utc':stamp,'home':norm(h),'away':norm(a),'name':g.get('game') or f'{a} at {h}','venue':'','source':'canonical_master'})
    return sorted(games,key=lambda x:x['date_utc'])

def fetch_schedule(cutoff):
    start=cutoff.strftime('%Y%m%d'); end=(cutoff+timedelta(days=75)).strftime('%Y%m%d')
    urls=[
        f'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?limit=1000&dates={start}-{end}',
        f'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?limit=1000&dates={cutoff.year}',
    ]
    errors=[]
    for url in urls:
        try:
            raw=get_json(url)
            return raw, url, errors
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
    return {'events':[]}, None, errors

def standings_strength():
    strength=defaultdict(lambda:.5)
    paths=[Path('data/dashboard/master_feed.json'),Path('data/dashboard/wnba_standings.json')]
    for p in paths:
        if not p.exists():continue
        try:d=json.load(p.open())
        except Exception:continue
        rows=d.get('standings',d if isinstance(d,list) else [])
        if isinstance(rows,dict):rows=rows.get('teams',[])
        for r in rows if isinstance(rows,list) else []:
            ab=norm(str(r.get('team_abbr') or r.get('abbreviation') or r.get('team') or ''))
            w=r.get('wins');l=r.get('losses');pct=r.get('win_pct') or r.get('winPercentage')
            try: strength[ab]=float(pct) if pct is not None else float(w)/(float(w)+float(l))
            except Exception:pass
    return strength

def scoreboard_strength(raw):
    strength=standings_strength()
    for event in raw.get('events',[]):
        for competition in event.get('competitions') or []:
            for competitor in competition.get('competitors') or []:
                team=norm(str((competitor.get('team') or {}).get('abbreviation') or ''))
                overall=next((r for r in competitor.get('records') or [] if r.get('type')=='total' or r.get('name')=='overall'),None)
                summary=str((overall or {}).get('summary') or '')
                try:
                    wins,losses=(int(x) for x in summary.split('-',1))
                    if team and wins+losses: strength[team]=wins/(wins+losses)
                except Exception: pass
    return strength

def build(games,strength=None):
    strength=strength or standings_strength(); by=defaultdict(list)
    for g in games:
        by[g['home']].append((g,False,g['away']));by[g['away']].append((g,True,g['home']))
    teams=[]
    for team,items in sorted(by.items()):
        prev=None; prev_loc=team; miles=0; b2b=0; three4=0; road=0; home=0; opp=[]; enriched=[]; dates=[]
        for g,is_away,op in items:
            dt=datetime.fromisoformat(g['date_utc']);dates.append(dt)
            loc=g['home'];m=hav(prev_loc,loc);miles+=m
            rest=None if prev is None else (dt.date()-prev.date()).days-1
            if rest==0:b2b+=1
            road+=int(is_away);home+=int(not is_away);opp.append(strength[op])
            enriched.append({'date_utc':g['date_utc'],'opponent':op,'site':'away' if is_away else 'home','rest_days':rest,'travel_miles':round(m,1),'back_to_back':rest==0})
            prev=dt;prev_loc=loc
        for i in range(len(dates)):
            if i>=2 and (dates[i].date()-dates[i-2].date()).days<=3:three4+=1
        sos=sum(opp)/len(opp) if opp else .5
        fatigue=round(b2b*12+three4*7+min(miles/500,25)+road*1.5,1)
        teams.append({'team':team,'remaining_games':len(items),'home_games':home,'road_games':road,'back_to_backs':b2b,'three_in_four':three4,'travel_miles':round(miles),'opponent_strength':round(sos,4),'schedule_difficulty':round(100*sos+fatigue*.35,1),'fatigue_index':fatigue,'next_games':enriched[:8]})
    rank=sorted(teams,key=lambda x:x['schedule_difficulty'],reverse=True)
    for i,x in enumerate(rank,1):x['difficulty_rank']=i
    return sorted(rank,key=lambda x:x['difficulty_rank'])

def main():
    now=datetime.now(timezone.utc); cutoff=target_date()
    raw,url,errors=fetch_schedule(cutoff)
    games=parse_events(raw,cutoff)
    coverage='full_api_window' if url else 'partial_repository_fallback'
    source=url or 'canonical_master_fallback'
    if not games:
        fallback=canonical_fallback(cutoff)
        if fallback:
            games=fallback
            coverage='partial_repository_fallback'
            source='canonical_master_fallback'
    teams=build(games,scoreboard_strength(raw))
    if url:
        status='ready' if games else 'ready_empty'
    else:
        status='degraded' if games else 'unavailable'
    payload={
        'generated_at_utc':now.isoformat(),
        'target_date':cutoff.isoformat(),
        'status':status,
        'source':source,
        'source_errors':errors,
        'coverage':coverage,
        'summary':{
            'remaining_games':len(games),'teams':len(teams),
            'first_game_utc':games[0]['date_utc'] if games else None,
            'last_game_utc':games[-1]['date_utc'] if games else None,
        },
        'hardest_schedules':teams[:5],
        'easiest_schedules':list(reversed(teams[-5:])),
        'teams':teams,'games':games,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps({'target_date':payload['target_date'],'status':status,'source':source,'coverage':coverage,**payload['summary']},indent=2))

if __name__=='__main__':main()
