"""V5-M09 portfolio + decision optimization.

Research-only portfolio construction over M05 walk-forward predictions. Uses the
M05 KNN research champion, archived prices, explicit conflict/exposure controls,
and conservative fractional-Kelly sizing. No production promotion occurs here.
"""
from __future__ import annotations
import csv,json,math
from collections import defaultdict
from pathlib import Path

SRC=Path('data/dashboard/wnba_v5_m05_predictions.csv')
OUTCSV=Path('data/dashboard/wnba_v5_portfolio.csv')
OUTJSON=Path('data/dashboard/wnba_v5_portfolio.json')
REPORT=Path('data/dashboard/wnba_v5_m09_report.json')
POLICY=Path('data/dashboard/wnba_v5_decision_engine.json')
EXPOSURE=Path('data/dashboard/wnba_v5_exposure_report.json')
CORR=Path('data/dashboard/wnba_v5_correlation_matrix.json')

MAX_GAME=3
MAX_PLAYER=2
MAX_DAILY_UNITS=5.0
MAX_BET_UNITS=0.5
KELLY_FRACTION=0.25
MIN_EV=0.02

def f(v,d=None):
    try:
        x=float(v);return x if math.isfinite(x) else d
    except Exception:return d

def implied(o):
    o=f(o)
    if o is None or o==0:return None
    return abs(o)/(abs(o)+100) if o<0 else 100/(o+100)
def profit_mult(o):
    o=f(o)
    if o is None or o==0:return None
    return 100/abs(o) if o<0 else o/100
def ev(p,o):
    b=profit_mult(o)
    return None if b is None else p*b-(1-p)
def kelly(p,o):
    b=profit_mult(o)
    if b is None:return 0.0
    q=1-p; raw=(b*p-q)/b
    return max(0.0,raw)*KELLY_FRACTION

def main():
    if not SRC.exists():raise SystemExit('M09_INPUT_MISSING')
    rows=list(csv.DictReader(SRC.open(encoding='utf-8-sig',newline='')))
    candidates=[]
    for r in rows:
        p=f(r.get('knn_probability'));o=f(r.get('american_odds'));line=f(r.get('alt_line'))
        if p is None or o is None:continue
        e=ev(p,o)
        if p<0.5 or e is None or e<MIN_EV:continue
        stake=min(MAX_BET_UNITS,round(kelly(p,o)*10,3))
        if stake<=0:continue
        rr=dict(r);rr.update({'v5_probability':p,'market_probability':implied(o),'expected_value':e,'expected_value_pct':e*100,'recommended_units':stake})
        candidates.append(rr)
    candidates.sort(key=lambda r:(f(r.get('expected_value'),-9),f(r.get('v5_probability'),0)),reverse=True)
    selected=[]; game_ct=defaultdict(int);player_ct=defaultdict(int);seen=set();daily=0.0;rejected=defaultdict(int)
    for r in candidates:
        key=(r.get('game_id'),str(r.get('player')).lower(),r.get('stat'),r.get('side'),r.get('alt_line'))
        if key in seen: rejected['DUPLICATE']+=1;continue
        g=str(r.get('game_id'));p=str(r.get('player')).lower()
        if game_ct[g]>=MAX_GAME: rejected['GAME_EXPOSURE']+=1;continue
        if player_ct[p]>=MAX_PLAYER: rejected['PLAYER_EXPOSURE']+=1;continue
        stake=f(r.get('recommended_units'),0)
        if daily+stake>MAX_DAILY_UNITS: rejected['DAILY_EXPOSURE']+=1;continue
        seen.add(key);game_ct[g]+=1;player_ct[p]+=1;daily+=stake;selected.append(r)
    pnl=0.0;peak=0.0;max_dd=0.0;wins=0
    for r in selected:
        y=int(float(r.get('target_win') or 0));stake=f(r.get('recommended_units'),0);mult=profit_mult(r.get('american_odds')) or 0
        rp=stake*mult if y else -stake;r['realized_units']=round(rp,4);pnl+=rp;wins+=y;peak=max(peak,pnl);max_dd=max(max_dd,peak-pnl)
    n=len(selected)
    report={'version':'V5','module':'V5-M09','stage':'PORTFOLIO_DECISION_OPTIMIZATION','status':'READY','research_only':True,'candidate_rows':len(candidates),'selected_rows':n,'wins':wins,'hit_rate':round(wins/n,6) if n else None,'profit_units':round(pnl,4),'staked_units':round(sum(f(r.get('recommended_units'),0) for r in selected),4),'roi_on_stake':round(pnl/max(1e-9,sum(f(r.get('recommended_units'),0) for r in selected)),6) if n else None,'max_drawdown_units':round(max_dd,4),'rejected_counts':dict(rejected),'limits':{'max_bets_per_game':MAX_GAME,'max_bets_per_player':MAX_PLAYER,'max_daily_units':MAX_DAILY_UNITS,'max_bet_units':MAX_BET_UNITS,'kelly_fraction':KELLY_FRACTION,'minimum_ev':MIN_EV},'production_promotion':False,'next_module':'V5-M10 Live Adaptive Decision Engine'}
    OUTCSV.parent.mkdir(parents=True,exist_ok=True)
    fields=list(selected[0].keys()) if selected else ['archive_index','game_date','game_id','player','stat','side','alt_line','american_odds','v5_probability','expected_value','recommended_units']
    with OUTCSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(selected)
    OUTJSON.write_text(json.dumps({'portfolio':selected,'report':report},indent=2)+'\n',encoding='utf-8')
    POLICY.write_text(json.dumps({'version':'V5-M09-policy-v1','research_only':True,'champion_probability':'KNN','minimum_ev':MIN_EV,'kelly_fraction':KELLY_FRACTION,'max_bet_units':MAX_BET_UNITS,'max_daily_units':MAX_DAILY_UNITS,'max_bets_per_game':MAX_GAME,'max_bets_per_player':MAX_PLAYER},indent=2)+'\n',encoding='utf-8')
    EXPOSURE.write_text(json.dumps({'game_exposure':dict(game_ct),'player_exposure':dict(player_ct),'total_units':round(daily,3)},indent=2)+'\n',encoding='utf-8')
    # Conservative structural dependency map; not a statistical correlation claim.
    pairs=[]
    for i,a in enumerate(selected):
        for b in selected[i+1:]:
            dep=0.0;reasons=[]
            if a.get('game_id')==b.get('game_id'):dep+=0.35;reasons.append('same_game')
            if str(a.get('player')).lower()==str(b.get('player')).lower():dep+=0.45;reasons.append('same_player')
            if a.get('stat')==b.get('stat'):dep+=0.10;reasons.append('same_stat')
            if dep:pairs.append({'a':a.get('archive_index'),'b':b.get('archive_index'),'dependency_score':round(min(1,dep),2),'reasons':reasons})
    CORR.write_text(json.dumps({'method':'structural dependency proxy, not empirical correlation','pairs':pairs},indent=2)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
