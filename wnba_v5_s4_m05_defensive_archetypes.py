"""WNBA V5 Operations Sprint 4 M05 - Defensive Archetypes.

Transforms S4-M01 opponent-defense profiles into interpretable, leakage-safe
archetype features and attaches them to S4-M04 ranked rows. Uses only fields
actually present in the certified defense store; pace/rim/transition labels are
never fabricated when those source metrics are unavailable.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

DASH = Path('data/dashboard')
PROFILES = DASH / 'wnba_v5_team_defense_profiles.csv'
POSITION = DASH / 'wnba_v5_team_defense_by_position.csv'
M01_REPORT = DASH / 'wnba_v5_s4_m01_report.json'
M04 = DASH / 'wnba_v5_rotation_intelligence.csv'
M04_REPORT = DASH / 'wnba_v5_s4_m04_report.json'
OUT_TEAM = DASH / 'wnba_v5_defensive_archetypes.csv'
OUT_MATCHUPS = DASH / 'wnba_v5_defensive_archetype_matchups.csv'
OUT_JSON = DASH / 'wnba_v5_defensive_archetypes.json'
OUT_REPORT = DASH / 'wnba_v5_s4_m05_report.json'


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def f(v, default=None):
    try: return float(v)
    except Exception: return default


def read_csv(path):
    if not path.exists(): return []
    try: return list(csv.DictReader(path.open(encoding='utf-8-sig', newline='')))
    except Exception: return []


def load_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception: return default


def band(index):
    if index is None: return 'UNAVAILABLE'
    if index <= 0.85: return 'ELITE_SUPPRESSION'
    if index <= 0.95: return 'STRONG_SUPPRESSION'
    if index < 1.05: return 'NEUTRAL'
    if index < 1.15: return 'VULNERABLE'
    return 'SEVERE_VULNERABILITY'


def trend_band(season, recent):
    if season in (None, 0) or recent is None: return 'UNAVAILABLE'
    d = recent / season - 1.0
    if d <= -0.10: return 'IMPROVING_FAST'
    if d <= -0.04: return 'IMPROVING'
    if d < 0.04: return 'STABLE'
    if d < 0.10: return 'DECLINING'
    return 'DECLINING_FAST'


def venue_band(home, away):
    if home is None or away is None or max(abs(home), abs(away)) == 0: return 'UNAVAILABLE'
    d = (home-away) / max((abs(home)+abs(away))/2.0, 1e-9)
    if d <= -0.10: return 'STRONGER_AT_HOME'
    if d >= 0.10: return 'STRONGER_AWAY'
    return 'BALANCED'


def stat_label(stat, idx):
    b = band(idx)
    names = {
        'PTS':'SCORING', '3PM':'PERIMETER', 'AST':'PLAYMAKING', 'REB':'REBOUNDING',
        'PRA':'ALL_AROUND', 'PA':'SCORING_PLAYMAKING', 'PR':'SCORING_REBOUNDING',
        'RA':'REBOUNDING_PLAYMAKING'
    }
    return f"{names.get(stat, stat)}_{b}"


def main():
    now = datetime.now(timezone.utc).isoformat()
    DASH.mkdir(parents=True, exist_ok=True)
    profiles = read_csv(PROFILES)
    pos = read_csv(POSITION)
    ranked = read_csv(M04)
    m01 = load_json(M01_REPORT,{})
    m04 = load_json(M04_REPORT,{})

    by_team = defaultdict(dict)
    for r in profiles:
        team = str(r.get('team') or '').strip(); stat = str(r.get('stat') or '').upper().strip()
        if team and stat: by_team[team][stat] = r

    pos_counts = Counter(norm(r.get('team')) for r in pos if r.get('team'))
    team_rows = []
    team_idx = {}
    for team in sorted(by_team):
        stats = by_team[team]
        indices = [f(r.get('defense_index')) for r in stats.values()]
        indices = [x for x in indices if x is not None]
        composite = mean(indices) if indices else None
        labels = []
        for stat in ('PTS','3PM','AST','REB','PRA','PA','PR','RA'):
            if stat in stats:
                labels.append(stat_label(stat, f(stats[stat].get('defense_index'))))
        # Select strongest and weakest stat families based on defense index.
        ordered = sorted(((stat, f(r.get('defense_index'))) for stat,r in stats.items() if f(r.get('defense_index')) is not None), key=lambda x:x[1])
        strength = ordered[0][0] if ordered else ''
        weakness = ordered[-1][0] if ordered else ''
        pts = stats.get('PTS',{}); three = stats.get('3PM',{}); ast = stats.get('AST',{}); reb = stats.get('REB',{})
        recent_vals=[]; season_vals=[]
        for r in stats.values():
            a=f(r.get('allowed_avg')); l5=f(r.get('last5_allowed_avg'))
            if a is not None and l5 is not None: season_vals.append(a); recent_vals.append(l5)
        trend = trend_band(mean(season_vals) if season_vals else None, mean(recent_vals) if recent_vals else None)
        homes=[f(r.get('home_allowed_avg')) for r in stats.values()]; aways=[f(r.get('away_allowed_avg')) for r in stats.values()]
        homes=[x for x in homes if x is not None]; aways=[x for x in aways if x is not None]
        venue = venue_band(mean(homes) if homes else None, mean(aways) if aways else None)
        overall = band(composite)
        archetype = f"{overall}|BEST_{strength or 'NA'}|WEAK_{weakness or 'NA'}|{trend}"
        row = {
            'team':team,'overall_defense_index':round(composite,4) if composite is not None else None,
            'overall_archetype':overall,'primary_strength_stat':strength,'primary_weakness_stat':weakness,
            'scoring_archetype':band(f(pts.get('defense_index'))),'perimeter_archetype':band(f(three.get('defense_index'))),
            'playmaking_archetype':band(f(ast.get('defense_index'))),'rebounding_archetype':band(f(reb.get('defense_index'))),
            'recent_defense_trend':trend,'venue_defense_profile':venue,'position_profile_rows':pos_counts.get(norm(team),0),
            'position_specific_available':pos_counts.get(norm(team),0)>0,'archetype_signature':archetype,
            'pace_archetype':'UNAVAILABLE_NO_SOURCE','rim_protection_archetype':'UNAVAILABLE_NO_SOURCE',
            'transition_defense_archetype':'UNAVAILABLE_NO_SOURCE','stat_archetypes':'|'.join(labels)
        }
        team_rows.append(row); team_idx[norm(team)] = row

    matchup_rows=[]; covered=0; missing_opp=0; missing_arch=0
    for r in ranked:
        opp=str(r.get('opponent') or '').strip(); a=team_idx.get(norm(opp)) if opp else None
        status='READY'
        if not opp: status='WAITING_FOR_OPPONENT'; missing_opp+=1
        elif not a: status='WAITING_FOR_ARCHETYPE'; missing_arch+=1
        else: covered+=1
        matchup_rows.append({
            'ranking_key':r.get('ranking_key'),'date':r.get('date'),'player':r.get('player'),'game':r.get('game'),
            'player_team':r.get('player_team'),'opponent':opp,'stat':r.get('stat'),'side':r.get('side'),
            'rotation_adjusted_projection':r.get('rotation_adjusted_projection'),'rotation_risk_band':r.get('rotation_risk_band'),
            'archetype_status':status,'opponent_overall_archetype':a.get('overall_archetype') if a else '',
            'opponent_archetype_signature':a.get('archetype_signature') if a else '',
            'opponent_primary_strength_stat':a.get('primary_strength_stat') if a else '',
            'opponent_primary_weakness_stat':a.get('primary_weakness_stat') if a else '',
            'opponent_recent_defense_trend':a.get('recent_defense_trend') if a else '',
            'opponent_venue_defense_profile':a.get('venue_defense_profile') if a else '',
            'stat_specific_archetype': stat_label(str(r.get('stat') or '').upper(), f(by_team.get(opp,{}).get(str(r.get('stat') or '').upper(),{}).get('defense_index'))) if a else '',
            'position_specific_available':a.get('position_specific_available') if a else False,
        })

    if not profiles: status='WAITING_FOR_M01_DEFENSE_PROFILES'
    elif not ranked: status='WAITING_FOR_M04_ROTATION_ROWS'
    elif covered==0: status='WAITING_FOR_MATCHABLE_ARCHETYPES'
    else: status='READY'
    coverage=round(100*covered/len(ranked),2) if ranked else 0.0
    dist=Counter(r['overall_archetype'] for r in team_rows)
    report={
        'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M05','stage':'DEFENSIVE_ARCHETYPES',
        'status':status,'generated_at_utc':now,'m01_status':m01.get('status'),'m04_status':m04.get('status'),
        'team_archetype_rows':len(team_rows),'ranked_rows':len(ranked),'archetype_ready_rows':covered,
        'archetype_coverage_pct':coverage,'missing_opponent_rows':missing_opp,'missing_archetype_rows':missing_arch,
        'overall_archetype_distribution':dict(dist),'position_profile_rows':len(pos),
        'available_dimensions':['SCORING','PERIMETER','PLAYMAKING','REBOUNDING','COMBO_MARKETS','RECENT_TREND','HOME_AWAY','POSITION_PROFILE_AVAILABILITY'],
        'unavailable_dimensions':['PACE','RIM_PROTECTION','TRANSITION_DEFENSE'],
        'methodology':'Archetypes are deterministic classifications of certified S4-M01 defense_index, last5 versus season allowed averages, and home/away splits. Lower defense_index means stronger suppression. M05 does not invent pace, rim, or transition metrics when absent.',
        'research_only':True,'production_ready':False,'next_module':'S4-M06 Referee Intelligence'
    }
    tf=list(team_rows[0].keys()) if team_rows else ['team']
    with OUT_TEAM.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=tf);w.writeheader();w.writerows(team_rows)
    mf=list(matchup_rows[0].keys()) if matchup_rows else ['ranking_key']
    with OUT_MATCHUPS.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=mf);w.writeheader();w.writerows(matchup_rows)
    OUT_JSON.write_text(json.dumps({'report':report,'teams':team_rows,'matchups':matchup_rows},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__': main()
