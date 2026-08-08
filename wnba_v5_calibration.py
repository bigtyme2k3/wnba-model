"""WNBA V5-M03: walk-forward calibration, probability bands, and research decision tiers.

Uses only out-of-sample M02 predictions. Calibration itself is also walk-forward:
for each prediction, the calibrator is fit only on earlier M02 predictions.
No production promotion occurs here; small samples remain research-only.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

IN=Path('data/dashboard/wnba_v5_probability_predictions.csv')
M02=Path('data/dashboard/wnba_v5_probability_status.json')
OUT_CSV=Path('data/dashboard/wnba_v5_calibrated_predictions.csv')
OUT_BANDS=Path('data/dashboard/wnba_v5_probability_bands.json')
OUT_THRESH=Path('data/dashboard/wnba_v5_decision_thresholds.json')
OUT_REPORT=Path('data/dashboard/wnba_v5_calibration_report.json')
OUT_MODEL=Path('data/warehouse/wnba_v5_calibration_model.json')

MIN_CAL_ROWS=30
EPS=1e-6


def clip(p): return min(1-EPS,max(EPS,float(p)))
def logit(p):
    p=clip(p); return math.log(p/(1-p))
def sigmoid(z):
    if z>=0:
        e=math.exp(-z); return 1/(1+e)
    e=math.exp(z); return e/(1+e)

def american_profit(odds):
    o=float(odds)
    return o/100.0 if o>0 else 100.0/abs(o)

def fit_platt(rows, steps=500, lr=0.03, reg=0.08):
    # Logistic calibration on logit(raw probability): sigmoid(a + b*logit(p)).
    a,b=0.0,1.0
    n=max(1,len(rows))
    for _ in range(steps):
        ga=gb=0.0
        for r in rows:
            x=logit(r['v5_probability']); y=r['target_win']; q=sigmoid(a+b*x)
            d=q-y; ga+=d; gb+=d*x
        ga=ga/n + reg*a
        gb=gb/n + reg*(b-1.0)
        a-=lr*ga; b-=lr*gb
    return a,b

def brier(rows,key):
    return sum((r[key]-r['target_win'])**2 for r in rows)/len(rows) if rows else None

def logloss(rows,key):
    if not rows:return None
    return -sum(r['target_win']*math.log(clip(r[key]))+(1-r['target_win'])*math.log(1-clip(r[key])) for r in rows)/len(rows)

def ece(rows,key,bins=5):
    if not rows:return None
    total=len(rows); ans=0.0
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        group=[r for r in rows if (lo<=r[key]<(hi if i<bins-1 else hi+EPS))]
        if group:
            conf=sum(r[key] for r in group)/len(group); acc=sum(r['target_win'] for r in group)/len(group)
            ans += len(group)/total*abs(conf-acc)
    return ans

def band_label(p):
    if p<.50:return '<50%'
    if p<.55:return '50-55%'
    if p<.60:return '55-60%'
    if p<.65:return '60-65%'
    if p<.70:return '65-70%'
    return '70%+'

def edge_band(e):
    if e<=0:return '<=0%'
    if e<.03:return '0-3%'
    if e<.07:return '3-7%'
    if e<.12:return '7-12%'
    return '12%+'

def summarize(group):
    n=len(group)
    if not n:return {'n':0}
    wins=sum(r['target_win'] for r in group)
    profit=sum(american_profit(r['american_odds']) if r['target_win'] else -1.0 for r in group)
    return {
        'n':n,'wins':wins,'losses':n-wins,'hit_rate':round(wins/n,6),
        'avg_calibrated_probability':round(sum(r['calibrated_probability'] for r in group)/n,6),
        'avg_market_probability':round(sum(r['market_probability'] for r in group)/n,6),
        'avg_probability_edge':round(sum(r['calibrated_edge'] for r in group)/n,6),
        'profit_units':round(profit,4),'roi':round(profit/n,6),
        'brier':round(brier(group,'calibrated_probability'),6)
    }

def main():
    m02=json.loads(M02.read_text())
    if m02.get('status')!='READY': raise SystemExit('M03_REQUIRES_READY_M02')
    raw=[]
    with IN.open(newline='',encoding='utf-8') as f:
        for x in csv.DictReader(f):
            raw.append({
                **x,
                'archive_index':int(x['archive_index']), 'prior_games':int(x['prior_games']),
                'target_win':int(x['target_win']), 'american_odds':float(x['american_odds']),
                'market_probability':float(x['market_probability']), 'v5_probability':float(x['v5_probability']),
                'train_rows':int(x['train_rows'])
            })
    raw.sort(key=lambda r:(r['game_date'],r['game_id'],r['archive_index']))
    calibrated=[]
    for i,r in enumerate(raw):
        if i<MIN_CAL_ROWS: continue
        history=raw[:i]
        a,b=fit_platt(history)
        cp=clip(sigmoid(a+b*logit(r['v5_probability'])))
        nr=dict(r)
        nr['calibration_train_rows']=i; nr['platt_intercept']=a; nr['platt_slope']=b
        nr['calibrated_probability']=cp; nr['calibrated_edge']=cp-r['market_probability']
        nr['probability_band']=band_label(cp); nr['edge_band']=edge_band(nr['calibrated_edge'])
        calibrated.append(nr)
    if not calibrated: raise SystemExit('M03_NO_CALIBRATED_ROWS')

    prob_groups=defaultdict(list); edge_groups=defaultdict(list)
    for r in calibrated:
        prob_groups[r['probability_band']].append(r); edge_groups[r['edge_band']].append(r)
    prob_order=['<50%','50-55%','55-60%','60-65%','65-70%','70%+']
    edge_order=['<=0%','0-3%','3-7%','7-12%','12%+']
    prob_summary={k:summarize(prob_groups[k]) for k in prob_order}
    edge_summary={k:summarize(edge_groups[k]) for k in edge_order}

    # Research tiers are evidence-gated. No tier above WATCH unless >=8 observations and positive ROI.
    thresholds=[]
    for k in edge_order:
        s=edge_summary[k]
        if s.get('n',0)<8: tier='RESEARCH_ONLY'
        elif k=='<=0%': tier='PASS'
        elif s['roi']<=0: tier='WATCH'
        elif k in ('0-3%','3-7%'): tier='WATCH'
        elif k=='7-12%': tier='BET_NOW'
        else: tier='ELITE'
        thresholds.append({'edge_band':k,'decision_tier':tier,**s})

    # Assign row tier from its edge band's evidence decision.
    tiermap={x['edge_band']:x['decision_tier'] for x in thresholds}
    for r in calibrated:r['research_decision']=tiermap[r['edge_band']]

    fields=['archive_index','game_date','game_id','player','stat','side','alt_line','american_odds','prior_games','target_win','market_probability','v5_probability','calibrated_probability','calibrated_edge','probability_band','edge_band','research_decision','calibration_train_rows']
    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in calibrated:w.writerow({k:r.get(k) for k in fields})

    last_a,last_b=fit_platt(raw)
    metrics={
        'calibrated_brier':round(brier(calibrated,'calibrated_probability'),6),
        'raw_v5_brier_same_rows':round(brier(calibrated,'v5_probability'),6),
        'market_brier_same_rows':round(brier(calibrated,'market_probability'),6),
        'calibrated_log_loss':round(logloss(calibrated,'calibrated_probability'),6),
        'raw_v5_log_loss_same_rows':round(logloss(calibrated,'v5_probability'),6),
        'market_log_loss_same_rows':round(logloss(calibrated,'market_probability'),6),
        'calibrated_ece_5bin':round(ece(calibrated,'calibrated_probability'),6),
        'raw_v5_ece_5bin_same_rows':round(ece(calibrated,'v5_probability'),6),
        'market_ece_5bin_same_rows':round(ece(calibrated,'market_probability'),6),
    }
    calibration_helped=metrics['calibrated_brier']<=metrics['raw_v5_brier_same_rows']
    report={
        'version':'V5','module':'V5-M03','stage':'CALIBRATION_PROBABILITY_BANDS','status':'READY',
        'm02_walk_forward_rows':len(raw),'calibrated_walk_forward_rows':len(calibrated),'minimum_calibration_history':MIN_CAL_ROWS,
        'metrics':metrics,'calibration_helped_brier':calibration_helped,
        'probability_bands':prob_summary,'edge_bands':edge_summary,
        'promotion_rule':'Research-only. Do not replace V4 production until larger out-of-sample sample and M04 EV/CLV validation.',
        'next_module':'V5-M04 Expected Value + CLV Validation'
    }
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    OUT_BANDS.write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),'probability_bands':prob_summary,'edge_bands':edge_summary},indent=2,allow_nan=False)+'\n')
    OUT_THRESH.write_text(json.dumps({'version':'V5','module':'V5-M03','research_only':True,'thresholds':thresholds},indent=2,allow_nan=False)+'\n')
    OUT_MODEL.parent.mkdir(parents=True,exist_ok=True)
    OUT_MODEL.write_text(json.dumps({'version':'V5','module':'V5-M03','method':'platt_logistic_on_logit_raw_probability','fit_rows':len(raw),'intercept':last_a,'slope':last_b,'minimum_walk_forward_calibration_rows':MIN_CAL_ROWS},indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
