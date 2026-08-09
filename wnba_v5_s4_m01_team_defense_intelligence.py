"""WNBA V5 Operations Sprint 4 M01 - Team Defense Intelligence.

Builds leakage-safe opponent defensive profiles from certified historical player-game
actuals already present in the V5 historical feature store. This module is descriptive
and research-only; it does not alter issued probabilities or promote V5.
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
OUT_PROFILE = DASH / 'wnba_v5_team_defense_profiles.csv'
OUT_JSON = DASH / 'wnba_v5_team_defense_intelligence.json'
OUT_POSITION = DASH / 'wnba_v5_team_defense_by_position.csv'
OUT_REPORT = DASH / 'wnba_v5_s4_m01_report.json'

SUPPORTED_STATS = {'PTS','REB','AST','3PM','PRA','PA','PR','RA'}


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def f(v):
    try:
        return float(v)
    except Exception:
        return None


def clean_date(v):
    s = str(v or '').strip()
    return s[:10] if len(s) >= 10 else ''


def parse_game(game):
    s = str(game or '').strip()
    for sep in (' @ ', ' vs. ', ' vs '):
        if sep in s:
            a,b = s.split(sep,1)
            return a.strip(), b.strip(), sep == ' @ '
    return '', '', False


def infer_opponent(row):
    for key in ('opp_team','opponent','opponent_team'):
        if row.get(key):
            return str(row[key]).strip(), None
    team = str(row.get('team') or '').strip()
    away, home, is_at = parse_game(row.get('game'))
    if not team or not away or not home:
        return '', None
    if norm(team) == norm(away):
        return home, 'HOME_DEFENSE' if is_at else None
    if norm(team) == norm(home):
        return away, 'AWAY_DEFENSE' if is_at else None
    return '', None


def pct_rank(values, x):
    vals = sorted(v for v in values if v is not None)
    if not vals or x is None:
        return None
    return round(100.0 * sum(v <= x for v in vals) / len(vals), 2)


def main():
    now = datetime.now(timezone.utc).isoformat()
    DASH.mkdir(parents=True, exist_ok=True)
    if not FEATURES.exists():
        report = {
            'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M01',
            'stage':'TEAM_DEFENSE_INTELLIGENCE','status':'WAITING_FOR_HISTORICAL_FEATURES',
            'generated_at_utc':now,'source':str(FEATURES),'profile_rows':0,
            'position_profile_rows':0,'research_only':True,'production_ready':False,
            'next_module':'S4-M02 Matchup Engine'
        }
        OUT_REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        OUT_JSON.write_text(json.dumps({'report':report,'profiles':[]},indent=2)+'\n',encoding='utf-8')
        for p in (OUT_PROFILE, OUT_POSITION):
            p.write_text('',encoding='utf-8')
        print(json.dumps(report,indent=2)); return

    raw = list(csv.DictReader(FEATURES.open(encoding='utf-8-sig',newline='')))
    observations = []
    seen=set()
    for r in raw:
        date = clean_date(r.get('game_date') or r.get('date'))
        player = str(r.get('player') or '').strip()
        stat = str(r.get('stat') or r.get('market') or '').upper().strip()
        actual = f(r.get('target_actual') if r.get('target_actual') not in (None,'') else r.get('actual'))
        if not date or not player or stat not in SUPPORTED_STATS or actual is None:
            continue
        opponent, venue = infer_opponent(r)
        if not opponent:
            continue
        pos = str(r.get('position') or r.get('pos') or '').upper().strip()
        key=(date,norm(player),norm(opponent),stat)
        if key in seen:
            continue
        seen.add(key)
        observations.append({'date':date,'player':player,'opponent':opponent,'stat':stat,'actual':actual,'position':pos,'venue':venue})

    by_team_stat=defaultdict(list)
    by_team_stat_pos=defaultdict(list)
    dates_by_team=defaultdict(set)
    for o in observations:
        by_team_stat[(o['opponent'],o['stat'])].append(o)
        dates_by_team[o['opponent']].add(o['date'])
        if o['position']:
            by_team_stat_pos[(o['opponent'],o['stat'],o['position'])].append(o)

    league_by_stat=defaultdict(list)
    for o in observations:
        league_by_stat[o['stat']].append(o['actual'])
    league_avg={s:mean(v) for s,v in league_by_stat.items() if v}

    profiles=[]
    for (team,stat), rows in sorted(by_team_stat.items()):
        vals=[r['actual'] for r in rows]
        team_dates=sorted({r['date'] for r in rows})
        last10_dates=set(team_dates[-10:]); last5_dates=set(team_dates[-5:])
        last10=[r['actual'] for r in rows if r['date'] in last10_dates]
        last5=[r['actual'] for r in rows if r['date'] in last5_dates]
        home=[r['actual'] for r in rows if r.get('venue')=='HOME_DEFENSE']
        away=[r['actual'] for r in rows if r.get('venue')=='AWAY_DEFENSE']
        lg=league_avg.get(stat)
        avg=mean(vals)
        profiles.append({
            'team':team,'stat':stat,'games_sampled':len(team_dates),'player_observations':len(vals),
            'allowed_avg':round(avg,4),'league_avg':round(lg,4) if lg is not None else None,
            'defense_index':round(avg/lg,4) if lg not in (None,0) else None,
            'last5_allowed_avg':round(mean(last5),4) if last5 else None,
            'last10_allowed_avg':round(mean(last10),4) if last10 else None,
            'home_allowed_avg':round(mean(home),4) if home else None,
            'away_allowed_avg':round(mean(away),4) if away else None,
        })

    for stat in SUPPORTED_STATS:
        vals=[p['allowed_avg'] for p in profiles if p['stat']==stat]
        for p in profiles:
            if p['stat']==stat:
                # Lower allowed is stronger defense; strength percentile reverses allowed percentile.
                ar=pct_rank(vals,p['allowed_avg'])
                p['allowed_percentile']=ar
                p['defense_strength_percentile']=round(100.0-ar,2) if ar is not None else None

    pos_profiles=[]
    for (team,stat,pos), rows in sorted(by_team_stat_pos.items()):
        vals=[r['actual'] for r in rows]
        dates=sorted({r['date'] for r in rows})
        pos_profiles.append({'team':team,'stat':stat,'position':pos,'games_sampled':len(dates),'player_observations':len(vals),'allowed_avg':round(mean(vals),4)})

    fields=['team','stat','games_sampled','player_observations','allowed_avg','league_avg','defense_index','last5_allowed_avg','last10_allowed_avg','home_allowed_avg','away_allowed_avg','allowed_percentile','defense_strength_percentile']
    with OUT_PROFILE.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows([{k:r.get(k) for k in fields} for r in profiles])
    pfields=['team','stat','position','games_sampled','player_observations','allowed_avg']
    with OUT_POSITION.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=pfields); w.writeheader(); w.writerows([{k:r.get(k) for k in pfields} for r in pos_profiles])

    teams=sorted({p['team'] for p in profiles})
    stats=sorted({p['stat'] for p in profiles})
    report={
        'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M01','stage':'TEAM_DEFENSE_INTELLIGENCE',
        'status':'READY' if profiles else 'WAITING_FOR_MATCHABLE_OPPONENT_HISTORY','generated_at_utc':now,
        'source':str(FEATURES),'source_rows':len(raw),'unique_player_game_stat_observations':len(observations),
        'teams':len(teams),'stats':stats,'profile_rows':len(profiles),'position_profile_rows':len(pos_profiles),
        'position_coverage_available':bool(pos_profiles),
        'features':['allowed_avg','defense_index','last5_allowed_avg','last10_allowed_avg','home_allowed_avg','away_allowed_avg','defense_strength_percentile'],
        'methodology':'Deduplicated certified player-game-stat actuals are attributed to the opposing defense. Lower allowed values imply stronger defense. Recent windows are based on the opponent team game dates represented in the historical store.',
        'limitations':'Pace, defensive rating, opponent eFG%, rim/perimeter shot profile, and position splits are only available when those source fields exist; this module does not fabricate missing advanced team metrics.',
        'research_only':True,'production_ready':False,'next_module':'S4-M02 Matchup Engine'
    }
    OUT_JSON.write_text(json.dumps({'report':report,'profiles':profiles,'position_profiles':pos_profiles},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__': main()
