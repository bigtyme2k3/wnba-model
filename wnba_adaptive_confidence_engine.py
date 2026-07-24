from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path('data/warehouse/wnba_odds_warehouse_v2.sqlite')
EDGES = Path('data/dashboard/wnba_daily_edges.json')
OUTS = [Path('data/dashboard/wnba_adaptive_confidence.json'), Path('data/warehouse/wnba_adaptive_confidence.json')]
MIN_BIN = 150


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


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return max(0.0, center - margin), min(1.0, center + margin)


def load_historical_rows() -> list[dict[str, Any]]:
    if not DB.exists():
        return []
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'historical_edge_predictions' not in tables:
        conn.close()
        return []
    cols = {r[1] for r in conn.execute('PRAGMA table_info(historical_edge_predictions)')}
    score = 'edge_score' if 'edge_score' in cols else 'model_score' if 'model_score' in cols else None
    prob = 'predicted_probability' if 'predicted_probability' in cols else 'model_probability' if 'model_probability' in cols else None
    result = 'result' if 'result' in cols else 'grade' if 'grade' in cols else None
    if not result or (not score and not prob):
        conn.close()
        return []
    parts = [f'"{result}" AS result', f'"{score}" AS edge_score' if score else 'NULL AS edge_score', f'"{prob}" AS probability' if prob else 'NULL AS probability']
    raw = conn.execute(f'SELECT {", ".join(parts)} FROM historical_edge_predictions').fetchall()
    conn.close()
    rows=[]
    for r in raw:
        d=dict(r); outcome=str(d.get('result') or '').strip().lower()
        if outcome not in {'win','won','loss','lost'}:
            continue
        s=num(d.get('edge_score')); p=num(d.get('probability'))
        if p is not None and p > 1: p /= 100
        if s is None and p is not None: s=p*100
        if p is None and s is not None: p=s/100
        if s is None or p is None: continue
        rows.append({'score':s,'raw_probability':max(.001,min(.999,p)),'won':1 if outcome in {'win','won'} else 0})
    return rows


def make_quantile_bins(rows: list[dict[str, Any]], min_bin: int = MIN_BIN) -> list[dict[str, Any]]:
    ordered=sorted(rows,key=lambda r:r['score'])
    if not ordered: return []
    target=max(min_bin, math.ceil(len(ordered)/20))
    bins=[]
    i=0
    while i < len(ordered):
        j=min(len(ordered),i+target)
        if len(ordered)-j < min_bin and j < len(ordered): j=len(ordered)
        chunk=ordered[i:j]
        # Keep identical boundary scores together.
        while j < len(ordered) and ordered[j]['score'] == chunk[-1]['score']:
            chunk.append(ordered[j]); j+=1
        wins=sum(r['won'] for r in chunk); n=len(chunk)
        lo,hi=wilson(wins,n)
        bins.append({
            'score_min':round(min(r['score'] for r in chunk),4),
            'score_max':round(max(r['score'] for r in chunk),4),
            'score_mid':round(sum(r['score'] for r in chunk)/n,4),
            'sample_size':n,
            'wins':wins,
            'hit_rate':round(wins/n,5),
            'raw_probability_avg':round(sum(r['raw_probability'] for r in chunk)/n,5),
            'ci95_low':round(lo,5),
            'ci95_high':round(hi,5),
        })
        i=j
    return bins


def pav(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks=[]
    for p in points:
        blocks.append({'weight':p['sample_size'],'sum':p['hit_rate']*p['sample_size'],'items':[p]})
        while len(blocks)>=2 and blocks[-2]['sum']/blocks[-2]['weight'] > blocks[-1]['sum']/blocks[-1]['weight']:
            b=blocks.pop(); a=blocks.pop()
            blocks.append({'weight':a['weight']+b['weight'],'sum':a['sum']+b['sum'],'items':a['items']+b['items']})
    out=[]
    for b in blocks:
        rate=b['sum']/b['weight']
        for p in b['items']:
            q=dict(p); q['calibrated_probability']=round(rate,5); out.append(q)
    return out


def interpolate(score: float, curve: list[dict[str, Any]]) -> tuple[float, bool]:
    pts=sorted((float(x['score_mid']),float(x['calibrated_probability'])) for x in curve)
    if not pts: return max(.01,min(.99,score/100)), True
    outside=score < pts[0][0] or score > pts[-1][0]
    if score <= pts[0][0]: return pts[0][1], outside
    if score >= pts[-1][0]: return pts[-1][1], outside
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        if x1 <= score <= x2:
            t=(score-x1)/(x2-x1) if x2>x1 else 0
            return y1+t*(y2-y1), False
    return pts[-1][1], True


def evidence_count(row: dict[str, Any]) -> int:
    comps=row.get('components') or {}
    return sum(num(comps.get(k)) is not None and float(comps.get(k)) != 50 for k in ('projection','recent_form','season_history','clv','roi','market_value'))


def tier(prob: float, sample_strength: float, evidence: int, extrapolated: bool, ci_low: float | None) -> str:
    # Never promote extrapolated scores to HIGH; history does not validate that range.
    if not extrapolated and prob >= .62 and sample_strength >= 55 and evidence >= 4 and ci_low is not None and ci_low >= .55:
        return 'HIGH'
    if prob >= .55 and sample_strength >= 40 and evidence >= 2:
        return 'MODERATE'
    return 'LOW'


def nearest_ci(score: float, curve: list[dict[str, Any]]) -> tuple[float | None,float | None,int]:
    if not curve: return None,None,0
    p=min(curve,key=lambda x:abs(float(x['score_mid'])-score))
    return num(p.get('ci95_low')),num(p.get('ci95_high')),int(p.get('sample_size') or 0)


def build() -> dict[str, Any]:
    rows=load_historical_rows()
    raw_bins=make_quantile_bins(rows)
    curve=pav(raw_bins)
    total=len(rows)
    domain_min=min((r['score'] for r in rows),default=None)
    domain_max=max((r['score'] for r in rows),default=None)
    reliable=total>=500 and len(curve)>=5 and domain_min is not None and domain_max-domain_min>=3

    edges=load(EDGES,{})
    updated=[]; extrapolated_count=0
    for r in edges.get('top_edges',[]):
        q=dict(r); score=float(q.get('edge_score') or 0)
        cp,outside=interpolate(score,curve)
        lo,hi,local_n=nearest_ci(score,curve)
        comps=q.get('components') or {}; ss=num(comps.get('sample_strength')) or 0
        ec=evidence_count(q)
        q['raw_confidence']=q.get('confidence')
        q['calibrated_probability']=round(cp,5)
        q['calibration_ci95_low']=lo; q['calibration_ci95_high']=hi
        q['calibration_local_sample']=local_n
        q['calibration_extrapolated']=outside
        q['adaptive_confidence']=tier(cp,ss,ec,outside,lo)
        q['confidence']=q['adaptive_confidence']
        q['calibration_version']='sprint8.1-quantile-isotonic-v2'
        if outside:
            extrapolated_count+=1
            q.setdefault('missing_evidence',[])
            if 'score outside validated historical range' not in q['missing_evidence']:
                q['missing_evidence'].append('score outside validated historical range')
        updated.append(q)
    if isinstance(edges,dict) and updated:
        edges['top_edges']=updated
        edges['adaptive_confidence']={'applied':True,'version':'sprint8.1-quantile-isotonic-v2','curve_points':len(curve),'validated_score_range':[domain_min,domain_max],'extrapolated_candidates':extrapolated_count}
        json.dump(edges,EDGES.open('w',encoding='utf-8'),indent=2,allow_nan=False)

    moderate=min((x['score_mid'] for x in curve if x['calibrated_probability']>=.55 and x['sample_size']>=MIN_BIN),default=None)
    high=min((x['score_mid'] for x in curve if x['calibrated_probability']>=.62 and x['sample_size']>=MIN_BIN and x['ci95_low']>=.55),default=None)
    report={
        'sprint':8,
        'phase':'8.1-calibration-resolution-upgrade',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'ok' if curve else 'insufficient_data',
        'summary':{
            'calibration_records':total,
            'raw_bins':len(raw_bins),
            'curve_points':len(curve),
            'reliable_for_adaptive_use':reliable,
            'validated_score_min':round(domain_min,4) if domain_min is not None else None,
            'validated_score_max':round(domain_max,4) if domain_max is not None else None,
            'validated_score_span':round(domain_max-domain_min,4) if domain_min is not None else None,
            'moderate_score_threshold':round(moderate,2) if moderate is not None else None,
            'high_score_threshold':round(high,2) if high is not None else None,
            'daily_edges_updated':len(updated),
            'extrapolated_daily_edges':extrapolated_count,
        },
        'calibration_curve':curve,
        'confidence_policy':{
            'HIGH':'calibrated probability >= 62%, sample strength >= 55, evidence >= 4, lower 95% CI >= 55%, and score inside validated historical range',
            'MODERATE':'calibrated probability >= 55%, sample strength >= 40, evidence >= 2',
            'LOW':'all remaining candidates',
            'method':'individual reconstructed predictions grouped into minimum-sample quantile bins, then weighted isotonic calibration',
            'minimum_bin_sample':MIN_BIN,
            'extrapolation_rule':'Scores outside the historical domain are flagged and cannot receive HIGH confidence.',
            'warning':'Reconstructed history is research calibration and is not identical to predictions saved live before tipoff.'
        }
    }
    for path in OUTS:
        path.parent.mkdir(parents=True,exist_ok=True)
        json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(report['summary'],indent=2))
    return report


if __name__=='__main__':
    build()
