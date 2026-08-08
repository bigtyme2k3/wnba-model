"""V5-M04 expected-value and closing-line-value validation.

Consumes M03 walk-forward calibrated predictions. EV is computed from the archived
price available at prediction time. CLV is joined only when an actual closing
snapshot exists in the repository; missing CLV is explicitly reported, never
invented. Outputs are research-only and cannot promote V5 to production.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from pathlib import Path

PRED=Path('data/dashboard/wnba_v5_calibrated_predictions.csv')
CAL=Path('data/dashboard/wnba_v5_calibration_report.json')
SNAPS=Path('data/history/wnba_line_snapshots.jsonl')
OUT_CSV=Path('data/dashboard/wnba_v5_ev_validation.csv')
CLV_CSV=Path('data/dashboard/wnba_v5_clv_validation.csv')
BANDS=Path('data/dashboard/wnba_v5_edge_bands.json')
THRESH=Path('data/dashboard/wnba_v5_recommendation_thresholds.json')
REPORT=Path('data/dashboard/wnba_v5_m04_report.json')


def f(v, default=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default

def implied(odds):
    o=f(odds)
    if o is None or o==0: return None
    return abs(o)/(abs(o)+100.0) if o<0 else 100.0/(o+100.0)

def win_profit(odds):
    o=f(odds)
    if o is None or o==0: return None
    return 100.0/abs(o) if o<0 else o/100.0

def expected_value(p, odds):
    wp=win_profit(odds)
    if p is None or wp is None: return None
    return p*wp-(1.0-p)

def realized_units(win, odds):
    wp=win_profit(odds)
    if wp is None: return None
    return wp if int(win)==1 else -1.0

def edge_band(edge):
    if edge is None: return 'UNKNOWN'
    if edge<=0: return '<=0%'
    if edge<0.03: return '0-3%'
    if edge<0.07: return '3-7%'
    if edge<0.12: return '7-12%'
    return '12%+'

def ev_band(ev):
    if ev is None: return 'UNKNOWN'
    if ev<=0: return '<=0%'
    if ev<0.03: return '0-3%'
    if ev<0.07: return '3-7%'
    if ev<0.12: return '7-12%'
    return '12%+'

def norm(s): return str(s or '').strip().lower()

def read_snaps():
    rows=[]
    if not SNAPS.exists() or SNAPS.stat().st_size==0: return rows
    for line in SNAPS.read_text(encoding='utf-8').splitlines():
        try:
            r=json.loads(line)
            if isinstance(r,dict): rows.append(r)
        except Exception: pass
    return rows

def close_index(snaps):
    idx=defaultdict(list)
    for s in snaps:
        if norm(s.get('stage')) not in {'close','closing'}: continue
        key=(str(s.get('date') or ''),norm(s.get('player')),norm(s.get('stat')),norm(s.get('signal')))
        idx[key].append(s)
    for k in idx:
        idx[k].sort(key=lambda x:str(x.get('captured_at_utc') or ''))
    return idx

def close_price(s, side):
    return f(s.get('over_price') if norm(side)=='over' else s.get('under_price'))

def line_clv(open_line, close_line, side):
    ol=f(open_line); cl=f(close_line)
    if ol is None or cl is None: return None
    return cl-ol if norm(side)=='over' else ol-cl

def price_clv(open_odds, close_odds):
    op=implied(open_odds); cp=implied(close_odds)
    if op is None or cp is None: return None
    return op-cp

def summarize(rows, field):
    groups=defaultdict(list)
    for r in rows: groups[r.get(field,'UNKNOWN')].append(r)
    out={}
    order=['<=0%','0-3%','3-7%','7-12%','12%+','UNKNOWN']
    for key in order:
        xs=groups.get(key,[])
        if not xs: continue
        n=len(xs); wins=sum(int(x['target_win']) for x in xs)
        units=sum(x['realized_units'] for x in xs if x['realized_units'] is not None)
        evs=[x['expected_value'] for x in xs if x['expected_value'] is not None]
        clvs=[x['line_clv'] for x in xs if x['line_clv'] is not None]
        pclvs=[x['price_clv'] for x in xs if x['price_clv'] is not None]
        out[key]={
            'n':n,'wins':wins,'losses':n-wins,'hit_rate':round(wins/n,6),
            'profit_units':round(units,4),'roi':round(units/n,6),
            'avg_expected_value':round(sum(evs)/len(evs),6) if evs else None,
            'clv_rows':len(clvs) or len(pclvs),
            'avg_line_clv':round(sum(clvs)/len(clvs),6) if clvs else None,
            'avg_price_clv':round(sum(pclvs)/len(pclvs),6) if pclvs else None,
        }
    return out

def main():
    if not PRED.exists(): raise SystemExit('M04_INPUT_MISSING: calibrated predictions')
    rows=[]
    with PRED.open(encoding='utf-8',newline='') as fh:
        for r in csv.DictReader(fh):
            p=f(r.get('calibrated_probability')); odds=f(r.get('american_odds')); win=int(float(r.get('target_win') or 0))
            mp=f(r.get('market_probability')); edge=f(r.get('calibrated_edge'))
            ev=expected_value(p,odds); ru=realized_units(win,odds)
            rows.append({**r,'target_win':win,'market_probability':mp,'calibrated_probability':p,'calibrated_edge':edge,
                         'expected_value':ev,'expected_value_pct':ev*100 if ev is not None else None,
                         'realized_units':ru,'ev_band':ev_band(ev),'m04_edge_band':edge_band(edge),
                         'closing_line':None,'closing_odds':None,'line_clv':None,'price_clv':None,'clv_available':False})
    snaps=read_snaps(); idx=close_index(snaps)
    for r in rows:
        key=(str(r.get('game_date') or ''),norm(r.get('player')),norm(r.get('stat')),norm(r.get('side')))
        opts=idx.get(key,[])
        if not opts: continue
        s=opts[-1]; co=close_price(s,r.get('side')); cl=f(s.get('line'))
        r['closing_line']=cl; r['closing_odds']=co
        r['line_clv']=line_clv(r.get('alt_line'),cl,r.get('side'))
        r['price_clv']=price_clv(r.get('american_odds'),co)
        r['clv_available']=r['line_clv'] is not None or r['price_clv'] is not None
    edge_summary=summarize(rows,'m04_edge_band'); ev_summary=summarize(rows,'ev_band')
    clv_rows=[r for r in rows if r['clv_available']]
    pos_ev=[r for r in rows if r['expected_value'] is not None and r['expected_value']>0]
    high_ev=[r for r in rows if r['expected_value'] is not None and r['expected_value']>=0.12]
    def perf(xs):
        if not xs:return {'n':0,'wins':0,'hit_rate':None,'profit_units':0.0,'roi':None}
        wins=sum(x['target_win'] for x in xs); units=sum(x['realized_units'] for x in xs)
        return {'n':len(xs),'wins':wins,'hit_rate':round(wins/len(xs),6),'profit_units':round(units,4),'roi':round(units/len(xs),6)}
    research={}
    for band,stats in ev_summary.items():
        n=stats['n']; roi=stats['roi']; aev=stats['avg_expected_value']
        tier='PASS'
        if n>=8 and aev is not None and aev>0 and roi is not None and roi>0: tier='WATCH'
        if n>=12 and aev is not None and aev>=0.07 and roi is not None and roi>=0.05: tier='BET_NOW_RESEARCH'
        if n>=15 and aev is not None and aev>=0.12 and roi is not None and roi>=0.10: tier='ELITE_RESEARCH'
        research[band]={'tier':tier,'evidence':stats}
    clv_cov=len(clv_rows)/len(rows) if rows else 0.0
    report={
        'version':'V5','module':'V5-M04','stage':'EXPECTED_VALUE_CLV_VALIDATION','status':'READY',
        'evaluation_rows':len(rows),'positive_ev_rows':len(pos_ev),'high_ev_12pct_rows':len(high_ev),
        'positive_ev_performance':perf(pos_ev),'high_ev_12pct_performance':perf(high_ev),
        'edge_bands':edge_summary,'ev_bands':ev_summary,
        'clv':{'snapshot_rows_total':len(snaps),'matched_rows':len(clv_rows),'coverage_pct':round(clv_cov*100,2),
               'status':'AVAILABLE' if clv_rows else 'UNAVAILABLE',
               'avg_line_clv':round(sum(r['line_clv'] for r in clv_rows if r['line_clv'] is not None)/max(1,sum(r['line_clv'] is not None for r in clv_rows)),6) if clv_rows else None,
               'avg_price_clv':round(sum(r['price_clv'] for r in clv_rows if r['price_clv'] is not None)/max(1,sum(r['price_clv'] is not None for r in clv_rows)),6) if clv_rows else None},
        'research_thresholds':research,
        'promotion_gate':{
            'production_promotion':False,
            'reason':'Research-only. Require larger out-of-sample sample and meaningful CLV coverage before replacing V4.',
            'minimum_future_evaluation_rows':300,'minimum_clv_coverage_pct':60.0,
        },
        'm03_context':json.loads(CAL.read_text(encoding='utf-8'))['metrics'] if CAL.exists() else {},
        'next_module':'V5-M05 Ensemble / Champion-Challenger Validation'
    }
    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0].keys()) if rows else []
    with OUT_CSV.open('w',encoding='utf-8',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=fields); w.writeheader(); w.writerows(rows)
    clv_fields=['archive_index','game_date','game_id','player','stat','side','alt_line','american_odds','closing_line','closing_odds','line_clv','price_clv','clv_available']
    with CLV_CSV.open('w',encoding='utf-8',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=clv_fields); w.writeheader(); w.writerows([{k:r.get(k) for k in clv_fields} for r in rows])
    BANDS.write_text(json.dumps({'edge_bands':edge_summary,'ev_bands':ev_summary},indent=2)+'\n',encoding='utf-8')
    THRESH.write_text(json.dumps({'research_only':True,'thresholds':research,'promotion_gate':report['promotion_gate']},indent=2)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
