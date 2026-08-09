"""WNBA V5 Operations Sprint 4 M03 - Lineup Intelligence.

Adds leakage-safe historical rotation/minutes context to S4-M02 matchup rows.
Uses only repository-local boxscores dated strictly before the opportunity date.
No live injury or confirmed-lineup status is fabricated when a source is absent.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

DASH=Path('data/dashboard')
RAW=Path('data/raw')
M02=DASH/'wnba_v5_matchup_adjustments.csv'
M02_REPORT=DASH/'wnba_v5_s4_m02_report.json'
OUT_CSV=DASH/'wnba_v5_lineup_adjustments.csv'
OUT_JSON=DASH/'wnba_v5_lineup_intelligence.json'
OUT_CONF=DASH/'wnba_v5_lineup_confidence.json'
OUT_REPORT=DASH/'wnba_v5_s4_m03_report.json'


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def f(v,default=None):
    try:return float(v)
    except Exception:return default

def b(v):
    return str(v or '').strip().lower() in {'1','true','yes','y'}

def clean_date(v):
    s=str(v or '').strip(); return s[:10] if len(s)>=10 else ''

def read_csv(path):
    if not path.exists():return []
    try:return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    except Exception:return []

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def build_history():
    hist=defaultdict(list); files=0; rows=0
    for path in sorted(RAW.glob('boxscores_*.csv')):
        files+=1
        for r in read_csv(path):
            date=clean_date(r.get('game_date')); player=norm(r.get('player')); team=str(r.get('team') or '').strip()
            mins=f(r.get('minutes')); starter=b(r.get('starter')); pos=str(r.get('position') or '').strip().upper()
            if not date or not player or not team or mins is None:continue
            hist[player].append({'date':date,'team':team,'minutes':mins,'starter':starter,'position':pos})
            rows+=1
    for k in hist: hist[k].sort(key=lambda x:x['date'])
    return hist,files,rows

def prior_rows(hist,player,target_date,team=None):
    rows=[r for r in hist.get(norm(player),[]) if r['date'] < target_date]
    if team:
        same=[r for r in rows if norm(r['team'])==norm(team)]
        if same: rows=same
    return rows

def avg(vals):
    vals=[x for x in vals if x is not None]
    return mean(vals) if vals else None

def main():
    now=datetime.now(timezone.utc).isoformat(); DASH.mkdir(parents=True,exist_ok=True)
    rows=read_csv(M02); m02=load_json(M02_REPORT,{})
    hist,files,history_rows=build_history()
    out=[]; ready=0; missing_hist=0; high=0; med=0; low=0
    for r in rows:
        date=clean_date(r.get('date')); player=str(r.get('player') or '').strip(); team=str(r.get('player_team') or '').strip()
        base=f(r.get('matchup_adjusted_projection'),f(r.get('raw_projection')))
        prior=prior_rows(hist,player,date,team)
        l10=prior[-10:]; l5=prior[-5:]
        mins_all=[x['minutes'] for x in prior]; mins10=[x['minutes'] for x in l10]; mins5=[x['minutes'] for x in l5]
        avg10=avg(mins10); avg5=avg(mins5); avgall=avg(mins_all)
        start10=avg([1.0 if x['starter'] else 0.0 for x in l10]); start5=avg([1.0 if x['starter'] else 0.0 for x in l5])
        pos=next((x['position'] for x in reversed(prior) if x.get('position')), '')
        if not prior:
            status='WAITING_FOR_ROTATION_HISTORY'; missing_hist+=1; mult=1.0; conf=0.0; band='LOW'; role='UNKNOWN'
        else:
            # Historical rotation signal only. Compare recent minutes to the player's prior baseline.
            ratio=(avg5/avgall) if avg5 is not None and avgall not in (None,0) else 1.0
            mult=max(0.90,min(1.10,1.0+0.35*(ratio-1.0)))
            n=len(prior); stability=1.0
            if len(mins10)>=2 and avg10 not in (None,0):
                stability=max(0.0,min(1.0,1.0-(pstdev(mins10)/max(avg10,1.0))))
            sample=min(1.0,n/10.0); conf=round(100*(0.55*sample+0.45*stability),2)
            if conf>=80:band='HIGH'; high+=1
            elif conf>=55:band='MEDIUM'; med+=1
            else:band='LOW'; low+=1
            sr=start5 if start5 is not None else start10
            role='STARTER' if sr is not None and sr>=0.6 else ('BENCH' if sr is not None and sr<=0.4 else 'MIXED')
            status='READY'; ready+=1
        adj=(base*mult) if base is not None else None
        out.append({
            'ranking_key':r.get('ranking_key'),'date':date,'player':player,'game':r.get('game'),'player_team':team,
            'opponent':r.get('opponent'),'stat':r.get('stat'),'side':r.get('side'),'position':pos,
            'matchup_projection':base,'rotation_games_prior':len(prior),'minutes_l5':round(avg5,3) if avg5 is not None else None,
            'minutes_l10':round(avg10,3) if avg10 is not None else None,'minutes_prior_mean':round(avgall,3) if avgall is not None else None,
            'starter_rate_l5':round(start5,3) if start5 is not None else None,'starter_rate_l10':round(start10,3) if start10 is not None else None,
            'projected_role':role,'injury_status':'UNAVAILABLE_NO_LIVE_SOURCE','lineup_confirmation':'UNAVAILABLE_NO_LIVE_SOURCE',
            'lineup_status':status,'lineup_confidence':conf,'lineup_confidence_band':band,
            'rotation_multiplier':round(mult,6),'lineup_adjusted_projection':round(adj,4) if adj is not None else None,
            'lineup_delta':round(adj-base,4) if adj is not None and base is not None else None,
            'adjustment_basis':'PRIOR_ONLY_ROTATION_MINUTES','live_injury_adjustment_applied':False,
        })
    if not rows:status='WAITING_FOR_M02_MATCHUPS'
    elif ready==0:status='WAITING_FOR_ROTATION_HISTORY'
    else:status='READY'
    coverage=round(100*ready/len(rows),2) if rows else 0.0
    report={
        'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M03','stage':'LINEUP_INTELLIGENCE',
        'status':status,'generated_at_utc':now,'m02_status':m02.get('status'),'rows':len(rows),'lineup_ready_rows':ready,
        'lineup_coverage_pct':coverage,'missing_rotation_history_rows':missing_hist,'boxscore_files_scanned':files,
        'boxscore_rotation_rows_scanned':history_rows,'confidence_bands':{'HIGH':high,'MEDIUM':med,'LOW':low+missing_hist},
        'live_injury_source_available':False,'confirmed_lineup_source_available':False,
        'methodology':'Strictly prior-date repository boxscores provide starter history and minutes. Recent minutes are shrunk toward the prior player baseline and capped to a 0.90-1.10 projection multiplier. No future boxscore, live injury, or confirmed lineup information is inferred.',
        'research_only':True,'production_ready':False,'next_module':'S4-M04 Rotation Intelligence'
    }
    fields=list(out[0].keys()) if out else ['ranking_key','date','player','game','player_team','opponent','stat','side','position','matchup_projection','rotation_games_prior','minutes_l5','minutes_l10','minutes_prior_mean','starter_rate_l5','starter_rate_l10','projected_role','injury_status','lineup_confirmation','lineup_status','lineup_confidence','lineup_confidence_band','rotation_multiplier','lineup_adjusted_projection','lineup_delta','adjustment_basis','live_injury_adjustment_applied']
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(out)
    conf={'generated_at_utc':now,'rows':len(out),'coverage_pct':coverage,'bands':report['confidence_bands'],'players':[{'player':r['player'],'team':r['player_team'],'role':r['projected_role'],'confidence':r['lineup_confidence'],'band':r['lineup_confidence_band'],'status':r['lineup_status']} for r in out]}
    OUT_JSON.write_text(json.dumps({'report':report,'lineups':out},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_CONF.write_text(json.dumps(conf,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':main()
