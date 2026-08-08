"""Phase 10: recover unresolved ALT player-games from official ESPN historical boxscores.

Non-destructive policy:
- never deletes or rewrites an existing warehouse record;
- appends only a uniquely resolved completed player-game;
- writes explicit canonical-resolution overrides for the archive finalizer;
- leaves ambiguous/postponed/DNP cases unresolved.
"""
from __future__ import annotations

import csv, json, math, re, time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

UNRESOLVED=Path('data/dashboard/wnba_alt_archive_unresolved_v3.csv')
AUDIT=Path('data/dashboard/wnba_alt_game_identity_audit.json')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
OUT=Path('data/dashboard/wnba_alt_phase10_historical_recovery.json')
OUT_CSV=Path('data/dashboard/wnba_alt_phase10_historical_recovery.csv')
OUT_W=Path('data/warehouse/wnba_alt_phase10_historical_recovery.json')
OVERRIDES=Path('data/warehouse/wnba_alt_phase10_official_resolutions.json')

S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 WNBA-model historical recovery'})
TEAM_ALIASES={
 'aces':'las vegas aces','dream':'atlanta dream','fever':'indiana fever','liberty':'new york liberty','lynx':'minnesota lynx',
 'mercury':'phoenix mercury','mystics':'washington mystics','sky':'chicago sky','sparks':'los angeles sparks','storm':'seattle storm',
 'sun':'connecticut sun','wings':'dallas wings','valkyries':'golden state valkyries','tempo':'toronto tempo','fire':'portland fire'
}

def norm(v:Any)->str:
    x=' '.join(str(v or '').strip().lower().replace('’',"'").split())
    return TEAM_ALIASES.get(x,x)

def num(v:Any):
    try:
        x=float(str(v).replace('%','')); return x if math.isfinite(x) else None
    except Exception:return None

def load(p:Path,default:Any):
    try:return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
    except Exception:return default

def save(p:Path,obj:Any):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def parse_game(g:str):
    g=str(g or '').replace(' vs. ',' @ ').replace(' vs ',' @ ')
    if '@' not in g:return ('','')
    a,b=g.split('@',1); return norm(a),norm(b)

def scoreboard(day:str):
    url='https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard'
    r=S.get(url,params={'dates':day.replace('-','')},timeout=20); r.raise_for_status()
    return r.json().get('events',[])

def event_teams(ev:dict):
    comp=(ev.get('competitions') or [{}])[0]
    home=away=''
    for c in comp.get('competitors',[]):
        name=((c.get('team') or {}).get('displayName') or (c.get('team') or {}).get('name') or '')
        if c.get('homeAway')=='home':home=norm(name)
        elif c.get('homeAway')=='away':away=norm(name)
    return away,home

def completed(ev:dict):
    st=((ev.get('status') or {}).get('type') or {})
    return bool(st.get('completed')) or norm(st.get('name')) in {'status_final','final'}

def summary(eid:str):
    url='https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary'
    r=S.get(url,params={'event':eid},timeout=20); r.raise_for_status(); return r.json()

def player_rows(payload:dict):
    out=[]
    for teamblock in ((payload.get('boxscore') or {}).get('players') or []):
        team=((teamblock.get('team') or {}).get('displayName') or (teamblock.get('team') or {}).get('name') or '')
        for statgroup in teamblock.get('statistics') or []:
            labels=[str(x).upper() for x in statgroup.get('labels') or []]
            for a in statgroup.get('athletes') or []:
                ath=a.get('athlete') or {}; name=ath.get('displayName') or ath.get('shortName') or ''
                vals=a.get('stats') or []
                d={labels[i]:vals[i] for i in range(min(len(labels),len(vals)))}
                if name: out.append((norm(name),name,team,d,ath.get('id')))
    return out

def made_attempt(v):
    if v is None:return (None,None)
    m=re.match(r'\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$',str(v))
    return (num(m.group(1)),num(m.group(2))) if m else (None,None)

def build_record(day,eid,away,home,found,method):
    _,name,team,d,pid=found
    fgm,fga=made_attempt(d.get('FG')); tpm,tpa=made_attempt(d.get('3PT') or d.get('3P')); ftm,fta=made_attempt(d.get('FT'))
    pts=num(d.get('PTS')); reb=num(d.get('REB')); ast=num(d.get('AST')); stl=num(d.get('STL')); blk=num(d.get('BLK')); tov=num(d.get('TO') or d.get('TOV')); pf=num(d.get('PF')); oreb=num(d.get('OREB')); dreb=num(d.get('DREB'))
    return {
      'record_id':f'{eid}|{pid or norm(name)}','game_id':str(eid),'event_id':str(eid),'game_date':day,
      'game':f'{away} @ {home}','player':name,'player_id':pid,'team':team,
      'scoring':{'total_pts':pts,'three_pm':tpm,'ftm':ftm,'fta':fta,'free_throw_points':ftm},
      'boxscore':{'reb':reb,'oreb':oreb,'dreb':dreb,'ast':ast,'stl':stl,'blk':blk,'tov':tov,'fgm':fgm,'fga':fga,'three_att':tpa},
      'fouls':{'total_committed':pf},'derived':{'pra':None if None in (pts,reb,ast) else pts+reb+ast,'pr':None if None in (pts,reb) else pts+reb,'pa':None if None in (pts,ast) else pts+ast,'ra':None if None in (reb,ast) else reb+ast},
      'phase10_recovered':True,'phase10_resolution_method':method,'source':'espn_official_boxscore_summary','recovered_at_utc':datetime.now(timezone.utc).isoformat()
    }

def candidate_days(row,diag):
    out=[]
    for v in [row.get('date'),diag.get('warehouse_date')]:
        if v and str(v)[:10] not in out: out.append(str(v)[:10])
    c=diag.get('candidate_dates') or []
    if isinstance(c,str):
        try:c=json.loads(c)
        except Exception:c=[x.strip() for x in c.split(',') if x.strip()]
    for v in c if isinstance(c,list) else []:
        if str(v)[:10] not in out:out.append(str(v)[:10])
    try:
        base=date.fromisoformat(str(row.get('date'))[:10])
        for delta in (-3,-2,-1,1,2,3):
            v=(base+timedelta(days=delta)).isoformat()
            if v not in out:out.append(v)
    except Exception:pass
    return out

def main():
    unresolved=list(csv.DictReader(UNRESOLVED.open(encoding='utf-8'))) if UNRESOLVED.exists() else []
    audit=load(AUDIT,{'records':[]}); diags={int(r.get('archive_index',i)):r for i,r in enumerate(audit.get('records',[])) if isinstance(r,dict)}
    logs=load(LOGS,{'records':[]}); records=[r for r in logs.get('records',[]) if isinstance(r,dict)]
    existing={(str(r.get('game_id') or r.get('event_id') or ''),norm(r.get('player') or r.get('player_name'))) for r in records}
    cache_events={}; cache_summary={}; results=[]; overrides={}; appended=[]; counts=Counter()
    for row in unresolved:
        idx=int(row.get('archive_index') or -1); diag=diags.get(idx,{})
        player=norm(row.get('player')); ga,gh=parse_game(row.get('game'))
        candidates=[]
        for day in candidate_days(row,diag):
            try: evs=cache_events.setdefault(day,scoreboard(day))
            except Exception as e:
                results.append({'archive_index':idx,'status':'FETCH_ERROR','detail':f'{day}: {e}'}); counts['FETCH_ERROR']+=1; continue
            for ev in evs:
                if not completed(ev):continue
                away,home=event_teams(ev); eid=str(ev.get('id') or '')
                exact_matchup=bool(ga and gh and away==ga and home==gh)
                same_day=day==str(row.get('date') or '')[:10]
                if not (exact_matchup or same_day):continue
                try: sm=cache_summary.setdefault(eid,summary(eid)); prows=player_rows(sm)
                except Exception:continue
                found=[p for p in prows if p[0]==player]
                if len(found)==1:
                    candidates.append({'day':day,'eid':eid,'away':away,'home':home,'found':found[0],'exact_matchup':exact_matchup,'same_day':same_day})
            time.sleep(0.02)
        # Deduplicate events.
        uniq={c['eid']:c for c in candidates}; candidates=list(uniq.values())
        preferred=[c for c in candidates if c['same_day'] and c['exact_matchup']]
        method='official_exact_same_date'
        if len(preferred)!=1:
            preferred=[c for c in candidates if c['same_day']]
            method='official_unique_player_game_same_date'
        if len(preferred)!=1:
            preferred=[c for c in candidates if c['exact_matchup']]
            method='official_unique_exact_matchup_near_date'
        if len(preferred)!=1:
            results.append({'archive_index':idx,'player':row.get('player'),'archive_date':row.get('date'),'archive_game':row.get('game'),'status':'AMBIGUOUS_OR_MISSING','candidate_event_ids':[c['eid'] for c in candidates],'candidate_dates':[c['day'] for c in candidates]});counts['AMBIGUOUS_OR_MISSING']+=1;continue
        c=preferred[0]; key=(c['eid'],player)
        if key not in existing:
            rec=build_record(c['day'],c['eid'],c['away'],c['home'],c['found'],method); records.append(rec);appended.append(rec);existing.add(key)
        overrides[str(idx)]={'archive_index':idx,'player':row.get('player'),'canonical_game_id':c['eid'],'canonical_game_date':c['day'],'canonical_game':f"{c['away']} @ {c['home']}",'resolution_method':method,'source':'espn_official_boxscore_summary'}
        results.append({'archive_index':idx,'player':row.get('player'),'archive_date':row.get('date'),'archive_game':row.get('game'),'status':'RESOLVED','canonical_game_id':c['eid'],'canonical_game_date':c['day'],'canonical_game':f"{c['away']} @ {c['home']}",'method':method,'warehouse_appended':key not in {(str(r.get('game_id') or ''),norm(r.get('player'))) for r in records[:-len(appended)]} if appended else False});counts['RESOLVED']+=1
    logs['records']=records; logs['phase10_recovered_records']=len(appended); logs['phase10_updated_at_utc']=datetime.now(timezone.utc).isoformat(); save(LOGS,logs)
    save(OVERRIDES,{'generated_at_utc':datetime.now(timezone.utc).isoformat(),'resolutions':overrides,'count':len(overrides)})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input_unresolved':len(unresolved),'resolved':len(overrides),'warehouse_appended':len(appended),'status_counts':dict(counts),'records':results}
    save(OUT,report);save(OUT_W,report)
    fields=sorted({k for r in results for k in r}) if results else ['archive_index','status']
    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for r in results:w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()})
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))

if __name__=='__main__':main()
