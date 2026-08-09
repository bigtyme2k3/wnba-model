"""WNBA V5 Operations Sprint 4 M04 - Rotation Intelligence.

Extends S4-M03 with leakage-safe workload stability features from repository boxscores.
Only games strictly before the target opportunity date are used. M04 measures minute
volatility, floor/ceiling, workload trend, starter consistency and role stability, then
applies a small confidence-aware workload multiplier. It does not infer injuries,
coach intent, or future rotations.
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
M03=DASH/'wnba_v5_lineup_adjustments.csv'
M03_REPORT=DASH/'wnba_v5_s4_m03_report.json'
OUT_CSV=DASH/'wnba_v5_rotation_intelligence.csv'
OUT_JSON=DASH/'wnba_v5_rotation_intelligence.json'
OUT_REPORT=DASH/'wnba_v5_s4_m04_report.json'
OUT_RISK=DASH/'wnba_v5_rotation_risk.json'


def norm(v): return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def f(v,default=None):
    try:return float(v)
    except Exception:return default
def b(v): return str(v or '').strip().lower() in {'1','true','yes','y'}
def clean_date(v):
    s=str(v or '').strip(); return s[:10] if len(s)>=10 else ''
def read_csv(path):
    if not path.exists(): return []
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
            mins=f(r.get('minutes')); starter=b(r.get('starter'))
            if not date or not player or not team or mins is None: continue
            hist[player].append({'date':date,'team':team,'minutes':mins,'starter':starter})
            rows+=1
    for p in hist: hist[p].sort(key=lambda x:x['date'])
    return hist,files,rows

def prior(hist,player,target_date,team=''):
    rows=[r for r in hist.get(norm(player),[]) if r['date'] < target_date]
    if team:
        same=[r for r in rows if norm(r['team'])==norm(team)]
        if same: rows=same
    return rows

def avg(vals): return mean(vals) if vals else None

def main():
    now=datetime.now(timezone.utc).isoformat(); DASH.mkdir(parents=True,exist_ok=True)
    rows=read_csv(M03); m03=load_json(M03_REPORT,{})
    hist,files,hrows=build_history()
    out=[]; ready=0; missing=0; stable=0; moderate=0; volatile=0
    for r in rows:
        date=clean_date(r.get('date')); player=str(r.get('player') or '').strip(); team=str(r.get('player_team') or '').strip()
        base=f(r.get('lineup_adjusted_projection'),f(r.get('matchup_projection')))
        h=prior(hist,player,date,team); l10=h[-10:]; l5=h[-5:]
        mins=[x['minutes'] for x in l10]; mins5=[x['minutes'] for x in l5]
        if not h:
            status='WAITING_FOR_ROTATION_HISTORY'; missing+=1
            m10=sd=cv=floor=ceiling=trend=None; starter_consistency=None; stability_score=0.0; risk='UNKNOWN'; mult=1.0
        else:
            m10=avg(mins); m5=avg(mins5)
            sd=pstdev(mins) if len(mins)>=2 else 0.0
            cv=(sd/m10) if m10 not in (None,0) else None
            ordered=sorted(mins)
            floor=ordered[max(0,int(round((len(ordered)-1)*0.20)))] if ordered else None
            ceiling=ordered[min(len(ordered)-1,int(round((len(ordered)-1)*0.80)))] if ordered else None
            if len(l5)>=2:
                xs=list(range(len(l5))); ys=[x['minutes'] for x in l5]
                xm=mean(xs); ym=mean(ys); den=sum((x-xm)**2 for x in xs)
                trend=(sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den) if den else 0.0
            else: trend=0.0
            starts=[1.0 if x['starter'] else 0.0 for x in l10]
            sr=avg(starts)
            starter_consistency=max(sr,1.0-sr) if sr is not None else None
            sample=min(1.0,len(h)/10.0)
            volatility_component=max(0.0,min(1.0,1.0-(cv if cv is not None else 1.0)))
            role_component=starter_consistency if starter_consistency is not None else 0.5
            stability_score=round(100*(0.45*sample+0.35*volatility_component+0.20*role_component),2)
            if stability_score>=80: risk='STABLE'; stable+=1
            elif stability_score>=60: risk='MODERATE'; moderate+=1
            else: risk='VOLATILE'; volatile+=1
            # Small workload-only adjustment to avoid double counting M03. Recent workload
            # relative to L10 baseline is shrunk heavily and capped at +/-5%.
            ratio=(m5/m10) if m5 is not None and m10 not in (None,0) else 1.0
            confidence=min(1.0,stability_score/100.0)
            mult=1.0 + 0.20*(ratio-1.0)*confidence
            mult=max(0.95,min(1.05,mult))
            status='READY'; ready+=1
        adj=(base*mult) if base is not None else None
        out.append({
            'ranking_key':r.get('ranking_key'),'date':date,'player':player,'game':r.get('game'),'player_team':team,
            'opponent':r.get('opponent'),'stat':r.get('stat'),'side':r.get('side'),'projected_role':r.get('projected_role'),
            'lineup_projection':base,'rotation_games_prior':len(h),'minutes_l5':round(avg(mins5),3) if mins5 else None,
            'minutes_l10':round(m10,3) if m10 is not None else None,'minutes_sd_l10':round(sd,3) if sd is not None else None,
            'minutes_cv_l10':round(cv,4) if cv is not None else None,'minutes_floor_p20':floor,'minutes_ceiling_p80':ceiling,
            'minutes_trend_l5':round(trend,4) if trend is not None else None,
            'starter_consistency_l10':round(starter_consistency,4) if starter_consistency is not None else None,
            'rotation_stability_score':stability_score,'rotation_risk_band':risk,'rotation_status':status,
            'workload_multiplier':round(mult,6),'rotation_adjusted_projection':round(adj,4) if adj is not None else None,
            'rotation_delta':round(adj-base,4) if adj is not None and base is not None else None,
            'injury_source_used':False,'coach_intent_inferred':False,'adjustment_basis':'PRIOR_ONLY_WORKLOAD_STABILITY'
        })
    status='WAITING_FOR_M03_LINEUPS' if not rows else ('WAITING_FOR_ROTATION_HISTORY' if ready==0 else 'READY')
    coverage=round(100*ready/len(rows),2) if rows else 0.0
    report={
        'version':'V5','sprint':'OPERATIONS_SPRINT_4','module':'S4-M04','stage':'ROTATION_INTELLIGENCE',
        'status':status,'generated_at_utc':now,'m03_status':m03.get('status'),'rows':len(rows),
        'rotation_ready_rows':ready,'rotation_coverage_pct':coverage,'missing_rotation_history_rows':missing,
        'risk_bands':{'STABLE':stable,'MODERATE':moderate,'VOLATILE':volatile,'UNKNOWN':missing},
        'boxscore_files_scanned':files,'boxscore_rotation_rows_scanned':hrows,
        'methodology':'Strictly prior-date boxscores measure L5/L10 minutes, volatility, floor/ceiling, trend and starter consistency. Workload adjustment is heavily shrunk and capped to 0.95-1.05 to avoid double counting M03. Injuries and coach intent are never inferred.',
        'live_injury_source_available':False,'research_only':True,'production_ready':False,
        'next_module':'S4-M05 Defensive Archetypes'
    }
    fields=list(out[0].keys()) if out else ['ranking_key','date','player','game','player_team','opponent','stat','side','projected_role','lineup_projection','rotation_games_prior','minutes_l5','minutes_l10','minutes_sd_l10','minutes_cv_l10','minutes_floor_p20','minutes_ceiling_p80','minutes_trend_l5','starter_consistency_l10','rotation_stability_score','rotation_risk_band','rotation_status','workload_multiplier','rotation_adjusted_projection','rotation_delta','injury_source_used','coach_intent_inferred','adjustment_basis']
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(out)
    OUT_JSON.write_text(json.dumps({'report':report,'rotations':out},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_RISK.write_text(json.dumps({'generated_at_utc':now,'risk_bands':report['risk_bands'],'players':[{'player':r['player'],'team':r['player_team'],'risk':r['rotation_risk_band'],'stability_score':r['rotation_stability_score'],'minutes_l5':r['minutes_l5'],'minutes_l10':r['minutes_l10']} for r in out]},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__': main()
