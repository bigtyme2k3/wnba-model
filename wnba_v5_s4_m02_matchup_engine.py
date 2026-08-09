"""WNBA V5 Operations Sprint 4 M02 - matchup intelligence engine.

Consumes current opportunity rankings plus S4-M01 team-defense profiles and
produces matchup-adjusted research features. Player-team identity is resolved
from explicit board fields first, then from S4-M01 certified historical context.
A historical team is accepted only when it is one of the two teams named in the
opportunity game, so trades or stale mappings cannot silently create an opponent.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
WARE=Path('data/warehouse')
RANKINGS=WARE/'wnba_opportunity_rankings.json'
DEF_PROFILES=DASH/'wnba_v5_team_defense_profiles.csv'
DEF_REPORT=DASH/'wnba_v5_s4_m01_report.json'
HIST_CONTEXT=DASH/'wnba_v5_historical_team_context.csv'
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
def clean_date(v):
    s=str(v or '').strip(); return s[:10] if len(s)>=10 else ''
def f(v,default=None):
    try:return float(v)
    except Exception:return default
def read_csv(path):
    if not path.exists():return []
    try:return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    except Exception:return []
def read_profiles():return read_csv(DEF_PROFILES)
def teams_from_game(game):
    s=str(game or '').replace(' vs. ',' @ ').replace(' vs ',' @ ')
    parts=[p.strip() for p in s.split('@') if p.strip()]
    return parts[:2] if len(parts)>=2 else []

def build_player_history():
    """Return player -> dated certified team observations from M01 context."""
    idx=defaultdict(list)
    for r in read_csv(HIST_CONTEXT):
        player=norm(r.get('player')); team=str(r.get('player_team') or '').strip(); date=clean_date(r.get('game_date'))
        if player and team and date:
            idx[player].append((date,team))
    for player in idx:
        # Dedupe repeated stat rows while preserving deterministic date/team history.
        idx[player]=sorted(set(idx[player]),key=lambda x:(x[0],norm(x[1])))
    return idx

def explicit_player_team(r):
    for k in ('player_team','team','team_name','player_team_name'):
        if r.get(k):return str(r.get(k)).strip(),'BOARD_EXPLICIT'
    return None,None

def resolve_player_team(r,history):
    """Resolve team conservatively and require membership in the named game."""
    teams=teams_from_game(r.get('game'))
    if len(teams)!=2:return None,'NO_GAME_TEAMS'
    explicit,source=explicit_player_team(r)
    if explicit:
        for t in teams:
            if norm(t)==norm(explicit):return t,source
        return None,'BOARD_TEAM_NOT_IN_GAME'

    player=norm(r.get('player')); target=clean_date(r.get('date'))
    candidates=history.get(player,[])
    if not candidates:return None,'NO_CERTIFIED_TEAM_HISTORY'

    # Prefer an exact-date certified team observation.
    exact=[]
    if target:
        exact=[team for date,team in candidates if date==target and any(norm(team)==norm(t) for t in teams)]
    if exact:
        uniq={norm(x):x for x in exact}
        if len(uniq)==1:
            resolved=next(iter(uniq.values()))
            return next(t for t in teams if norm(t)==norm(resolved)),'CERTIFIED_EXACT_DATE'

    # Otherwise use the latest prior certified team only if it is one of the game teams.
    prior=[(date,team) for date,team in candidates if (not target or date<=target) and any(norm(team)==norm(t) for t in teams)]
    if prior:
        latest_date=max(date for date,_ in prior)
        latest={norm(team):team for date,team in prior if date==latest_date}
        if len(latest)==1:
            resolved=next(iter(latest.values()))
            return next(t for t in teams if norm(t)==norm(resolved)),'CERTIFIED_LATEST_PRIOR'
    return None,'NO_UNAMBIGUOUS_TEAM_IN_GAME'

def resolve_opponent(r,team):
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
    history=build_player_history()
    idx={(norm(r.get('team')),str(r.get('stat') or '').upper()):r for r in profiles}

    out=[]; unresolved_team=0; unresolved_def=0; adjusted=0
    source_counts=defaultdict(int)
    for r in ranked:
        stat=str(r.get('market') or r.get('stat') or '').upper()
        raw=f(r.get('model_projection'))
        team,team_source=resolve_player_team(r,history)
        source_counts[team_source or 'UNKNOWN']+=1
        opp=resolve_opponent(r,team)
        prof=idx.get((norm(opp),stat)) if opp else None
        row={
            'ranking_key':r.get('ranking_key'),'date':r.get('date'),'player':r.get('player'),'game':r.get('game'),
            'player_team':team,'player_team_source':team_source,'opponent':opp,'stat':stat,'side':str(r.get('side') or '').upper(),
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

    if not ranked:status='WAITING_FOR_OPPORTUNITY_BOARD'
    elif not profiles:status='WAITING_FOR_M01_DEFENSE_PROFILES'
    elif adjusted==0 and unresolved_team:status='WAITING_FOR_PLAYER_TEAM_MAPPING'
    elif adjusted==0:status='WAITING_FOR_MATCHABLE_DEFENSE_PROFILES'
    else:status='READY'

    coverage=round(100.0*adjusted/len(ranked),2) if ranked else 0.0
    report={
        'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M02','stage':'MATCHUP_INTELLIGENCE_ENGINE',
        'status':status,'generated_at_utc':now,'ranked_rows':len(ranked),'m01_profile_rows':len(profiles),
        'historical_player_team_names':len(history),'matchup_adjusted_rows':adjusted,'matchup_coverage_pct':coverage,
        'unresolved_player_team_rows':unresolved_team,'unresolved_defense_profile_rows':unresolved_def,
        'player_team_source_counts':dict(sorted(source_counts.items())),'m01_status':m01.get('status'),
        'methodology':'Player team is explicit when present; otherwise exact-date then latest-prior certified S4-M01 team history is accepted only when that team appears in the named game. Defense adjustment uses the S4-M01 defense_index with 50% shrinkage and a hard 0.85-1.15 cap.',
        'research_only':True,'production_ready':False,'next_module':'S4-M03 Lineup Intelligence'
    }
    fields=list(out[0].keys()) if out else ['ranking_key','date','player','game','player_team','player_team_source','opponent','stat','side','raw_projection','best_line','model_probability','matchup_status','defense_allowed_avg','league_allowed_avg','defense_index','last5_allowed_avg','last10_allowed_avg','home_allowed_avg','away_allowed_avg','matchup_multiplier','matchup_adjusted_projection','matchup_delta']
    DASH.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(out)
    OUT_JSON.write_text(json.dumps({'report':report,'matchups':out},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':main()
