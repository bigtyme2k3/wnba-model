from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAL = Path('data/dashboard/wnba_confidence_calibration.json')
EDGES = Path('data/dashboard/wnba_daily_edges.json')
OUTS = [Path('data/dashboard/wnba_adaptive_confidence.json'), Path('data/warehouse/wnba_adaptive_confidence.json')]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def score_mid(label: str) -> float | None:
    label = str(label or '')
    if label == '90+': return 95.0
    if label == '<50': return 45.0
    if '-' in label:
        try:
            a,b = label.split('-',1)
            return (float(a)+float(b))/2
        except Exception:
            return None
    return None


def pav(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks=[]
    for p in points:
        blocks.append({'weight':p['sample_size'],'sum':p['hit_rate']*p['sample_size'],'items':[p]})
        while len(blocks) >= 2 and blocks[-2]['sum']/blocks[-2]['weight'] > blocks[-1]['sum']/blocks[-1]['weight']:
            b=blocks.pop(); a=blocks.pop()
            blocks.append({'weight':a['weight']+b['weight'],'sum':a['sum']+b['sum'],'items':a['items']+b['items']})
    out=[]
    for b in blocks:
        rate=b['sum']/b['weight']
        for p in b['items']:
            q=dict(p); q['calibrated_probability']=round(rate,4); out.append(q)
    return out


def interpolate(score: float, curve: list[dict[str, Any]]) -> float:
    if not curve: return max(.01,min(.99,score/100))
    pts=sorted((float(x['score_mid']),float(x['calibrated_probability'])) for x in curve)
    if score <= pts[0][0]: return pts[0][1]
    if score >= pts[-1][0]: return pts[-1][1]
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        if x1 <= score <= x2:
            t=(score-x1)/(x2-x1) if x2>x1 else 0
            return y1+t*(y2-y1)
    return max(.01,min(.99,score/100))


def tier(prob: float, sample_strength: float | None = None, evidence_count: int | None = None) -> str:
    ss = sample_strength if sample_strength is not None else 0
    ec = evidence_count if evidence_count is not None else 0
    if prob >= .62 and ss >= 55 and ec >= 4: return 'HIGH'
    if prob >= .55 and ss >= 40 and ec >= 2: return 'MODERATE'
    return 'LOW'


def build() -> dict[str, Any]:
    cal=load(CAL,{})
    raw=[]
    for r in cal.get('by_score_band',[]):
        mid=score_mid(r.get('group'))
        n=int(r.get('sample_size') or 0)
        hr=num(r.get('hit_rate'))
        if mid is None or n <= 0 or hr is None: continue
        raw.append({'score_band':r.get('group'),'score_mid':mid,'sample_size':n,'hit_rate':hr,'roi':num(r.get('roi')),'units':num(r.get('units'))})
    raw.sort(key=lambda x:x['score_mid'])
    curve=pav(raw)

    total=sum(x['sample_size'] for x in curve)
    reliable=total >= 300 and len(curve) >= 2
    high_threshold=None; moderate_threshold=None
    for x in curve:
        if moderate_threshold is None and x['calibrated_probability'] >= .55 and x['sample_size'] >= 30:
            moderate_threshold=x['score_mid']
        if high_threshold is None and x['calibrated_probability'] >= .62 and x['sample_size'] >= 50:
            high_threshold=x['score_mid']
    if moderate_threshold is None: moderate_threshold=68.0
    if high_threshold is None: high_threshold=82.0

    edges=load(EDGES,{})
    updated=[]
    for r in edges.get('top_edges',[]):
        q=dict(r)
        score=float(q.get('edge_score') or 0)
        cp=interpolate(score,curve)
        comps=q.get('components') or {}
        evidence=sum(float(comps.get(k,50)) != 50 for k in ('projection','recent_form','season_history','clv','roi','market_value'))
        q['raw_confidence']=q.get('confidence')
        q['calibrated_probability']=round(cp,4)
        q['adaptive_confidence']=tier(cp,num(comps.get('sample_strength')),evidence)
        q['confidence']=q['adaptive_confidence']
        q['calibration_version']='sprint8-isotonic-v1'
        updated.append(q)
    if isinstance(edges,dict) and updated:
        edges['top_edges']=updated
        edges['adaptive_confidence']={'applied':True,'version':'sprint8-isotonic-v1','curve_points':len(curve)}
        json.dump(edges,EDGES.open('w',encoding='utf-8'),indent=2,allow_nan=False)

    report={
        'sprint':8,
        'phase':'adaptive-confidence-engine',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'ok' if curve else 'insufficient_data',
        'summary':{
            'calibration_records':total,
            'curve_points':len(curve),
            'reliable_for_adaptive_use':reliable,
            'moderate_score_threshold':round(moderate_threshold,2),
            'high_score_threshold':round(high_threshold,2),
            'daily_edges_updated':len(updated),
        },
        'calibration_curve':curve,
        'confidence_policy':{
            'HIGH':'calibrated probability >= 62%, sample strength >= 55, evidence count >= 4',
            'MODERATE':'calibrated probability >= 55%, sample strength >= 40, evidence count >= 2',
            'LOW':'all remaining candidates',
            'method':'weighted isotonic regression over historical score bands',
            'warning':'Historical reconstruction lacks original live timestamps for every row; use as adaptive research calibration, not proof of live predictive performance.'
        }
    }
    for path in OUTS:
        path.parent.mkdir(parents=True,exist_ok=True)
        json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(report['summary'],indent=2))
    return report


if __name__=='__main__':
    build()
