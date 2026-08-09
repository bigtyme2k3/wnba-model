"""WNBA V5 Operations Sprint 4 M02 - matchup intelligence engine.

Consumes current opportunity rankings plus S4-M01 team-defense profiles and
produces matchup-adjusted research features. This module never fabricates
opponent identity or defensive data; if either is unavailable it reports a
waiting state and leaves the raw projection unchanged.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
WARE=Path('data/warehouse')
RANKINGS=WARE/'wnba_opportunity_rankings.json'
DEF_PROFILES=DASH/'wnba_v5_team_defense_profiles.csv'
DEF_REPORT=DASH/'wnba_v5_s4_m01_report.json'
OUT_CSV=DASH/'wnba_v5_matchup_adjustments.csv'
OUT_JSON=DASH/'wnba_v5_matchup_intelligence.json'
OUT_REPORT=DASH/'wnba_v5_s4_m02_report.json'


def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def rows_of(p):
    if not isinstance(p,dict):return []
    for key in ('all_ranked','top_opportunities','opportunities','rows'):
        v=p.get(key)
        if isinstance(v,list) and v:return v
    return []

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def f(v,default=None):
    try:return float(v)
    except Exception:return default

def read_profiles():
    if not DEF_PROFILES.exists():return []
    try:return list(csv.DictReader(DEF_PROFILES.open(encoding='utf-8-sig',newline='')))
    except Exception:return []

def teams_from_game(game):
    s=str(game or '').replace(' vs. ',' @ ').replace(' vs ',' @ ')
    parts=[p.strip() for p in s.split('@') if p.strip()]
    return parts[:2] if len(parts)>=2 else []

def resolve_player_team(r):
    for k in ('player_team','team','team_name','player_team_name'):
        if r.get(k):return str(r.get(k)).strip()
    return None

def resolve_opponent(r):
    team=resolve_player_team(r)
    teams=teams_from_game(r.get('game'))
    if not team or len(teams)!=2:return None
    nt=norm(team)
    if norm(teams[0])==nt:return teams[1]
    if norm(teams[1])==nt:return teams[0]
    return None

def main():
    now=datetime.now(timezone.utc).isoformat()
    board=load_json(RANKINGS,{})
    ranked=rows_of(board)
    profiles=read_profiles()
    m01=load_json(DEF_REPORT,{})
    idx={(norm(r.get('team')),str(r.get('stat') or '').upper()):r for r in profiles}

    out=[]; unresolved_team=0; unresolved_def=0; adjusted=0
    for r in ranked:
        stat=str(r.get('market') or r.get('stat') or '').upper()
        raw=f(r.get('model_projection'))
        team=resolve_player_team(r)
        opp=resolve_opponent(r)
        prof=idx.get((norm(opp),stat)) if opp else None
        row={
            'ranking_key':r.get('ranking_key'),'date':r.get('date'),'player':r.get('player'),'game':r.get('game'),
            'player_team':team,'opponent':opp,'stat':stat,'side':str(r.get('side') or '').upper(),
            'raw_projection':raw,'best_line':f(r.get('best_line')),'model_probability':f(r.get('model_probability')),
            'matchup_status':'READY','defense_allowed_avg':None,'league_allowed_avg':None,'defense_index':None,
            'last5_allowed_avg':None,'last10_allowed_avg':None,'home_allowed_avg':None,'away_allowed_avg':None,
            'matchup_multiplier':1.0,'matchup_adjusted_projection':raw,'matchup_delta':0.0,
        }
        if not team or not opp:
            row['matchup_status']='WAITING_FOR_PLAYER_TEAM_MAPPING';unresolved_team+=1
        elif not prof:
            row['matchup_status']='WAITING_FOR_DEFENSE_PROFILE';unresolved_def+=1
        else:
            di=f(prof.get('defense_index'),1.0)
            # Conservative shrinkage: apply half of the league-relative defensive
            # deviation so sparse opponent samples cannot dominate the projection.
            mult=1.0 + 0.5*((di or 1.0)-1.0)
            mult=max(0.85,min(1.15,mult))
            adj=(raw*mult) if raw is not None else None
            row.update({
                'defense_allowed_avg':f(prof.get('allowed_avg')),
                'league_allowed_avg':f(prof.get('league_avg')),
                'defense_index':di,
                'last5_allowed_avg':f(prof.get('last5_allowed_avg')),
                'last10_allowed_avg':f(prof.get('last10_allowed_avg')),
                'home_allowed_avg':f(prof.get('home_allowed_avg')),
                'away_allowed_avg':f(prof.get('away_allowed_avg')),
                'matchup_multiplier':round(mult,6),
                'matchup_adjusted_projection':round(adj,4) if adj is not None else None,
                'matchup_delta':round(adj-raw,4) if adj is not None and raw is not None else None,
            })
            adjusted+=1
        out.append(row)

    if not ranked:
        status='WAITING_FOR_OPPORTUNITY_BOARD'
    elif not profiles:
        status='WAITING_FOR_M01_DEFENSE_PROFILES'
    elif adjusted==0 and unresolved_team:
        status='WAITING_FOR_PLAYER_TEAM_MAPPING'
    elif adjusted==0:
        status='WAITING_FOR_MATCHABLE_DEFENSE_PROFILES'
    else:
        status='READY'

    report={
        'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M02','stage':'MATCHUP_INTELLIGENCE_ENGINE',
        'status':status,'generated_at_utc':now,'ranked_rows':len(ranked),'m01_profile_rows':len(profiles),
        'matchup_adjusted_rows':adjusted,'unresolved_player_team_rows':unresolved_team,
        'unresolved_defense_profile_rows':unresolved_def,'m01_status':m01.get('status'),
        'methodology':'Matchup adjustment uses the S4-M01 league-relative defense_index with 50% shrinkage and a hard 0.85-1.15 cap. Missing opponent/team data never causes an inferred adjustment.',
        'research_only':True,'production_ready':False,'next_module':'S4-M03 Lineup Intelligence'
    }
    fields=list(out[0].keys()) if out else ['ranking_key','date','player','game','player_team','opponent','stat','side','raw_projection','best_line','model_probability','matchup_status','defense_allowed_avg','league_allowed_avg','defense_index','last5_allowed_avg','last10_allowed_avg','home_allowed_avg','away_allowed_avg','matchup_multiplier','matchup_adjusted_projection','matchup_delta']
    DASH.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(out)
    OUT_JSON.write_text(json.dumps({'report':report,'matchups':out},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':main()
