"""WNBA V5 certified historical feature engine.

Builds a leakage-safe feature store from the protected canonical ALT archive.
Only PRIMARY + CERTIFIED observations are eligible. Every rolling feature uses
player/stat actuals from strictly earlier canonical games; same-game results are
never visible to that game's features.
"""
from __future__ import annotations

import csv, json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANON=Path('data/history/wnba_alt_streak_history_v3.jsonl')
HEALTH=Path('data/dashboard/wnba_alt_archive_health.json')
OUT=Path('data/warehouse/wnba_v5_historical_features.json')
OUTCSV=Path('data/dashboard/wnba_v5_historical_features.csv')
STATUS=Path('data/dashboard/wnba_v5_status.json')


def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def num(v:Any):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def american_implied(v:Any):
    x=num(v)
    if x is None or x==0:return None
    return (-x)/((-x)+100.0) if x<0 else 100.0/(x+100.0)

def line_hit(actual:float,line:float,side:str):
    s=str(side or '').upper()
    if s=='OVER':
        return 1.0 if actual>line else (0.5 if actual==line else 0.0)
    if s=='UNDER':
        return 1.0 if actual<line else (0.5 if actual==line else 0.0)
    return None

def mean(xs):
    return sum(xs)/len(xs) if xs else None

def stdev(xs):
    return statistics.pstdev(xs) if len(xs)>=2 else (0.0 if len(xs)==1 else None)

def slope(xs):
    n=len(xs)
    if n<2:return None
    xm=(n-1)/2; ym=mean(xs)
    den=sum((i-xm)**2 for i in range(n))
    return sum((i-xm)*(y-ym) for i,y in enumerate(xs))/den if den else 0.0

def read_rows():
    return [json.loads(x) for x in CANON.read_text(encoding='utf-8').splitlines() if x.strip()]

def game_date(r):
    return str(r.get('canonical_game_date') or r.get('warehouse_date') or r.get('date') or '')[:10]

def actual_value(r):
    for k in ('canonical_actual','actual','result_value'):
        v=num(r.get(k))
        if v is not None:return v
    return None

def odds_value(r):
    for k in ('best_odds','odds','price','american_odds'):
        if r.get(k) not in (None,''):return num(r.get(k))
    return None

def score_value(r):
    for k in ('score','model_score','alt_score'):
        v=num(r.get(k))
        if v is not None:return v
    return None

def score_band(v):
    if v is None:return 'UNKNOWN'
    if v>=80:return '80+'
    if v>=75:return '75-79.9'
    if v>=70:return '70-74.9'
    if v>=60:return '60-69.9'
    return 'BELOW_60'

def main():
    health=json.loads(HEALTH.read_text(encoding='utf-8'))
    if health.get('status')!='HEALTHY_LOCKED':
        raise SystemExit('V5_FEATURE_STORE_BLOCKED: canonical archive is not HEALTHY_LOCKED')
    rows=read_rows()
    eligible=[]
    for i,r in enumerate(rows):
        if r.get('canonical_status')!='CERTIFIED':continue
        if r.get('canonical_observation_status') not in (None,'PRIMARY'):continue
        actual=actual_value(r); line=num(r.get('alt_line'))
        if actual is None or line is None:continue
        rr=dict(r); rr['_archive_index']=i; eligible.append(rr)
    eligible.sort(key=lambda r:(game_date(r),str(r.get('canonical_game_id') or ''),norm(r.get('player')),str(r.get('stat') or ''),num(r.get('alt_line')) or 0))

    histories=defaultdict(list)  # (player, stat) -> one actual per completed game
    features=[]
    # Process a same player/stat/game bundle together so no observation can see same-game actual.
    bundles=defaultdict(list)
    order=[]
    for r in eligible:
        k=(game_date(r),str(r.get('canonical_game_id') or ''),norm(r.get('player')),str(r.get('stat') or '').upper())
        if k not in bundles:order.append(k)
        bundles[k].append(r)

    for bundle_key in order:
        bundle=bundles[bundle_key]
        sample=bundle[0]
        pkey=(norm(sample.get('player')),str(sample.get('stat') or '').upper())
        prior=list(histories[pkey])
        prior_actuals=[x['actual'] for x in prior]
        for r in bundle:
            line=float(num(r.get('alt_line'))); side=str(r.get('side') or '').upper(); actual=float(actual_value(r))
            h5=prior_actuals[-5:]; h10=prior_actuals[-10:]
            past_hits=[line_hit(x,line,side) for x in prior_actuals]
            past_hits=[x for x in past_hits if x is not None]
            market_odds=odds_value(r); implied=american_implied(market_odds)
            outcome=str(r.get('canonical_outcome') or r.get('outcome') or '').upper()
            target=1 if outcome=='WIN' else (0 if outcome=='LOSS' else None)
            score=score_value(r)
            f={
                'archive_index':r['_archive_index'],
                'game_date':game_date(r),
                'game_id':str(r.get('canonical_game_id') or ''),
                'player':r.get('player'),
                'stat':str(r.get('stat') or '').upper(),
                'side':side,
                'alt_line':line,
                'american_odds':market_odds,
                'market_implied_probability':implied,
                'model_score':score,
                'score_band':score_band(score),
                'prior_games':len(prior_actuals),
                'prior_actual_mean':mean(prior_actuals),
                'prior_actual_std':stdev(prior_actuals),
                'prior_actual_min':min(prior_actuals) if prior_actuals else None,
                'prior_actual_max':max(prior_actuals) if prior_actuals else None,
                'rolling3_actual_mean':mean(prior_actuals[-3:]),
                'rolling5_actual_mean':mean(h5),
                'rolling10_actual_mean':mean(h10),
                'rolling5_actual_std':stdev(h5),
                'rolling10_actual_std':stdev(h10),
                'rolling5_trend_slope':slope(h5),
                'rolling10_trend_slope':slope(h10),
                'line_minus_prior_mean':None if not prior_actuals else line-mean(prior_actuals),
                'historical_hit_rate_at_current_line':mean(past_hits),
                'historical_hit_rate_l5_at_current_line':mean([line_hit(x,line,side) for x in h5]),
                'historical_hit_rate_l10_at_current_line':mean([line_hit(x,line,side) for x in h10]),
                'target_actual':actual,
                'target_win':target,
                'canonical_outcome':outcome,
                'certification':'PRIMARY_CERTIFIED',
            }
            features.append(f)
        # one actual update per completed player/stat/game
        histories[pkey].append({'date':bundle_key[0],'game_id':bundle_key[1],'actual':float(actual_value(sample))})

    payload={
        'schema':'wnba-v5-historical-features-v1',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_archive':str(CANON),
        'archive_health_status':health.get('status'),
        'source_canonical_rows':health.get('canonical_rows'),
        'source_certified_rows':health.get('certified_rows'),
        'source_coverage_pct':health.get('coverage_pct'),
        'feature_rows':len(features),
        'players':len({norm(x['player']) for x in features}),
        'stats':sorted({x['stat'] for x in features}),
        'leakage_policy':'rolling features use strictly prior canonical games; same-game actuals are withheld until all observations for that player/stat/game are emitted',
        'records':features,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    fields=list(features[0].keys()) if features else []
    OUTCSV.parent.mkdir(parents=True,exist_ok=True)
    with OUTCSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(features)
    usable=sum(1 for x in features if x['target_win'] is not None and x['prior_games']>=3)
    status={
        'version':'V5',
        'stage':'HISTORICAL_FEATURE_STORE',
        'status':'READY' if features and usable else 'INSUFFICIENT_DATA',
        'feature_rows':len(features),
        'training_eligible_rows_min3_prior_games':usable,
        'players':payload['players'],
        'stats':payload['stats'],
        'archive_health':health.get('status'),
        'archive_coverage_pct':health.get('coverage_pct'),
        'next_module':'V5-M02 Probability Learner',
    }
    STATUS.write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(status,indent=2))

if __name__=='__main__':main()
