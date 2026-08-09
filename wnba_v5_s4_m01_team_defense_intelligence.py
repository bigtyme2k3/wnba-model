"""WNBA V5 Operations Sprint 4 M01 - Team Defense Intelligence.

Builds leakage-safe opponent defensive profiles from certified historical player-game
actuals. Historical feature rows are enriched from repository-local game context,
raw score files, and boxscore sources using immutable game_id/player joins. No
team/opponent is guessed.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

DASH = Path('data/dashboard')
FEATURES = DASH / 'wnba_v5_historical_features.csv'
GAME_CONTEXT = Path('data/warehouse/sprint22/game_context.csv')
RAW = Path('data/raw')
OUT_PROFILE = DASH / 'wnba_v5_team_defense_profiles.csv'
OUT_JSON = DASH / 'wnba_v5_team_defense_intelligence.json'
OUT_POSITION = DASH / 'wnba_v5_team_defense_by_position.csv'
OUT_REPORT = DASH / 'wnba_v5_s4_m01_report.json'
OUT_CONTEXT = DASH / 'wnba_v5_historical_team_context.csv'
OUT_RECOVERY = DASH / 'wnba_v5_s4_m01_schedule_recovery.json'

SUPPORTED_STATS = {'PTS','REB','AST','3PM','PRA','PA','PR','RA'}


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def f(v):
    try: return float(v)
    except Exception: return None


def clean_date(v):
    s=str(v or '').strip()
    return s[:10] if len(s)>=10 else ''


def read_csv(path):
    if not path.exists(): return []
    try: return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    except Exception: return []


def build_game_index():
    """Build exact game_id -> home/away identity from trusted repository sources.

    Primary source is the consolidated warehouse game_context. Missing identities are
    recovered from repository raw scores files. Exact game_id is required; no fuzzy or
    date-only opponent inference is allowed.
    """
    idx={}; source_by_gid={}; context_rows=0; score_files=0; score_rows=0; recovered=0
    for r in read_csv(GAME_CONTEXT):
        context_rows += 1
        gid=str(r.get('game_id') or '').strip()
        home=str(r.get('home_team') or '').strip(); away=str(r.get('away_team') or '').strip()
        if gid and home and away:
            idx[gid]={'home_team':home,'away_team':away,'game_date':clean_date(r.get('game_date'))}
            source_by_gid[gid]='warehouse_game_context'

    score_paths=sorted({*RAW.glob('scores_*.csv'), *( [RAW/'scores.csv'] if (RAW/'scores.csv').exists() else [] )})
    for path in score_paths:
        score_files += 1
        for r in read_csv(path):
            score_rows += 1
            gid=str(r.get('game_id') or '').strip()
            home=str(r.get('home_team') or '').strip(); away=str(r.get('away_team') or '').strip()
            if not gid or not home or not away:
                continue
            if gid not in idx:
                idx[gid]={'home_team':home,'away_team':away,'game_date':clean_date(r.get('game_date'))}
                source_by_gid[gid]=f'raw_scores:{path.name}'
                recovered += 1
            else:
                # Never silently overwrite a conflicting exact identity.
                old=idx[gid]
                if norm(old['home_team'])!=norm(home) or norm(old['away_team'])!=norm(away):
                    source_by_gid[gid]=source_by_gid.get(gid,'')+'|CONFLICT_RAW_SCORES_IGNORED'
    return idx,source_by_gid,{
        'game_context_rows_scanned':context_rows,
        'raw_score_files_scanned':score_files,
        'raw_score_rows_scanned':score_rows,
        'recovered_game_ids_from_raw_scores':recovered,
    }


def build_player_game_index():
    idx={}; files=0; rows=0
    for path in sorted(RAW.glob('boxscores_*.csv')):
        files += 1
        for r in read_csv(path):
            gid=str(r.get('game_id') or '').strip(); player=norm(r.get('player'))
            team=str(r.get('team') or '').strip(); pos=str(r.get('position') or '').upper().strip()
            if gid and player and team:
                key=(gid,player)
                if key not in idx:
                    idx[key]={'team':team,'position':pos,'game_date':clean_date(r.get('game_date'))}
                elif norm(idx[key]['team'])==norm(team) and not idx[key].get('position') and pos:
                    idx[key]['position']=pos
                rows += 1
    return idx,files,rows


def resolve_context(r, games, source_by_gid, player_games):
    gid=str(r.get('game_id') or '').strip(); player=norm(r.get('player'))
    pg=player_games.get((gid,player),{})
    g=games.get(gid,{})
    team=str(r.get('team') or r.get('player_team') or pg.get('team') or '').strip()
    pos=str(r.get('position') or r.get('pos') or pg.get('position') or '').upper().strip()
    home=str(g.get('home_team') or '').strip(); away=str(g.get('away_team') or '').strip()
    opponent=''; venue=''
    if team and home and away:
        if norm(team)==norm(home): opponent=away; venue='AWAY_DEFENSE'
        elif norm(team)==norm(away): opponent=home; venue='HOME_DEFENSE'
    return team,opponent,venue,pos,home,away,source_by_gid.get(gid,'')


def pct_rank(values,x):
    vals=sorted(v for v in values if v is not None)
    if not vals or x is None:return None
    return round(100.0*sum(v<=x for v in vals)/len(vals),2)


def main():
    now=datetime.now(timezone.utc).isoformat(); DASH.mkdir(parents=True,exist_ok=True)
    raw=read_csv(FEATURES)
    games,game_sources,recovery_meta=build_game_index(); player_games,box_files,box_rows=build_player_game_index()

    observations=[]; seen=set(); context_rows=[]; unresolved=[]; resolved_via_raw_scores=0
    for r in raw:
        date=clean_date(r.get('game_date') or r.get('date')); gid=str(r.get('game_id') or '').strip()
        player=str(r.get('player') or '').strip(); stat=str(r.get('stat') or r.get('market') or '').upper().strip()
        actual=f(r.get('target_actual') if r.get('target_actual') not in (None,'') else r.get('actual'))
        if not date or not gid or not player or stat not in SUPPORTED_STATS or actual is None: continue
        team,opponent,venue,pos,home,away,game_source=resolve_context(r,games,game_sources,player_games)
        if team and opponent and game_source.startswith('raw_scores:'):
            resolved_via_raw_scores += 1
        context_rows.append({'game_date':date,'game_id':gid,'player':player,'player_team':team,'opponent_team':opponent,'home_team':home,'away_team':away,'home_away':'HOME' if team and norm(team)==norm(home) else ('AWAY' if team and norm(team)==norm(away) else ''),'position':pos,'stat':stat,'target_actual':actual,'schedule_source':game_source})
        if not team or not opponent:
            unresolved.append({'game_id':gid,'game_date':date,'player':player,'team':team,'home_team':home,'away_team':away,'schedule_source':game_source})
            continue
        key=(date,gid,norm(player),norm(opponent),stat)
        if key in seen: continue
        seen.add(key)
        observations.append({'date':date,'game_id':gid,'player':player,'team':team,'opponent':opponent,'stat':stat,'actual':actual,'position':pos,'venue':venue})

    cfields=['game_date','game_id','player','player_team','opponent_team','home_team','away_team','home_away','position','stat','target_actual','schedule_source']
    with OUT_CONTEXT.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=cfields); w.writeheader(); w.writerows([{k:r.get(k) for k in cfields} for r in context_rows])

    by=defaultdict(list); bypos=defaultdict(list); league=defaultdict(list)
    for o in observations:
        by[(o['opponent'],o['stat'])].append(o); league[o['stat']].append(o['actual'])
        if o['position']: bypos[(o['opponent'],o['stat'],o['position'])].append(o)
    league_avg={s:mean(v) for s,v in league.items() if v}

    profiles=[]
    for (team,stat),rows in sorted(by.items()):
        vals=[x['actual'] for x in rows]; dates=sorted({x['date'] for x in rows}); l5=set(dates[-5:]); l10=set(dates[-10:])
        v5=[x['actual'] for x in rows if x['date'] in l5]; v10=[x['actual'] for x in rows if x['date'] in l10]
        home=[x['actual'] for x in rows if x['venue']=='HOME_DEFENSE']; away=[x['actual'] for x in rows if x['venue']=='AWAY_DEFENSE']
        avg=mean(vals); lg=league_avg.get(stat)
        profiles.append({'team':team,'stat':stat,'games_sampled':len(dates),'player_observations':len(vals),'allowed_avg':round(avg,4),'league_avg':round(lg,4) if lg is not None else None,'defense_index':round(avg/lg,4) if lg not in (None,0) else None,'last5_allowed_avg':round(mean(v5),4) if v5 else None,'last10_allowed_avg':round(mean(v10),4) if v10 else None,'home_allowed_avg':round(mean(home),4) if home else None,'away_allowed_avg':round(mean(away),4) if away else None})
    for stat in SUPPORTED_STATS:
        vals=[p['allowed_avg'] for p in profiles if p['stat']==stat]
        for p in profiles:
            if p['stat']==stat:
                ar=pct_rank(vals,p['allowed_avg']); p['allowed_percentile']=ar; p['defense_strength_percentile']=round(100-ar,2) if ar is not None else None

    pos_profiles=[]
    for (team,stat,pos),rows in sorted(bypos.items()):
        vals=[x['actual'] for x in rows]; dates=sorted({x['date'] for x in rows})
        pos_profiles.append({'team':team,'stat':stat,'position':pos,'games_sampled':len(dates),'player_observations':len(vals),'allowed_avg':round(mean(vals),4)})

    fields=['team','stat','games_sampled','player_observations','allowed_avg','league_avg','defense_index','last5_allowed_avg','last10_allowed_avg','home_allowed_avg','away_allowed_avg','allowed_percentile','defense_strength_percentile']
    with OUT_PROFILE.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows([{k:r.get(k) for k in fields} for r in profiles])
    pfields=['team','stat','position','games_sampled','player_observations','allowed_avg']
    with OUT_POSITION.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=pfields); w.writeheader(); w.writerows([{k:r.get(k) for k in pfields} for r in pos_profiles])

    resolved=sum(1 for r in context_rows if r['player_team'] and r['opponent_team']); coverage=round(100*resolved/len(context_rows),2) if context_rows else 0.0
    teams=sorted({p['team'] for p in profiles}); stats=sorted({p['stat'] for p in profiles})
    status='READY' if profiles else ('WAITING_FOR_MATCHABLE_OPPONENT_HISTORY' if raw else 'WAITING_FOR_HISTORICAL_FEATURES')
    production_ready = bool(status=='READY' and coverage>=95.0)
    report={'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M01','stage':'TEAM_DEFENSE_INTELLIGENCE','status':status,'generated_at_utc':now,'source_rows':len(raw),'game_context_rows':len(games),'boxscore_files_scanned':box_files,'boxscore_rows_scanned':box_rows,**recovery_meta,'historical_context_rows':len(context_rows),'resolved_team_opponent_rows':resolved,'resolved_rows_via_raw_scores':resolved_via_raw_scores,'team_opponent_coverage_pct':coverage,'coverage_target_pct':95.0,'coverage_target_met':coverage>=95.0,'unresolved_team_opponent_rows':len(context_rows)-resolved,'unique_player_game_stat_observations':len(observations),'teams':len(teams),'stats':stats,'profile_rows':len(profiles),'position_profile_rows':len(pos_profiles),'position_coverage_available':bool(pos_profiles),'features':['allowed_avg','defense_index','last5_allowed_avg','last10_allowed_avg','home_allowed_avg','away_allowed_avg','defense_strength_percentile'],'context_methodology':'player team/position is joined by exact game_id + normalized player from repository boxscores; opponent and venue are joined by exact game_id, first from warehouse game_context and then from repository raw score files. No fuzzy or inferred opponent fallback is used.','limitations':'Advanced pace, defensive rating, opponent eFG%, rim/perimeter shot profile remain unavailable unless separately sourced.','unresolved_examples':unresolved[:10],'research_only':True,'production_ready':production_ready,'next_module':'S4-M02 Matchup Engine'}
    recovery={'generated_at_utc':now,'module':'S4-M01','coverage_before_patch_pct':68.67,'coverage_after_patch_pct':coverage,'coverage_target_pct':95.0,'coverage_target_met':coverage>=95.0,'recovered_game_ids_from_raw_scores':recovery_meta['recovered_game_ids_from_raw_scores'],'resolved_rows_via_raw_scores':resolved_via_raw_scores,'remaining_unresolved_rows':len(context_rows)-resolved,'unresolved_examples':unresolved[:25]}
    OUT_JSON.write_text(json.dumps({'report':report,'profiles':profiles,'position_profiles':pos_profiles},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_RECOVERY.write_text(json.dumps(recovery,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__': main()
