from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path('data/warehouse/wnba_odds_warehouse_v2.sqlite')
OUTS = [Path('data/dashboard/wnba_confidence_calibration.json'), Path('data/warehouse/wnba_confidence_calibration.json')]


def num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def norm(v: Any) -> str:
    return ' '.join(str(v or '').strip().lower().split())


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
    except Exception:
        return set()


def existing_tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def pick(cols: set[str], *names: str) -> str | None:
    for n in names:
        if n in cols:
            return n
    return None


def profit_units(result: str, odds: float | None) -> float:
    r = norm(result)
    if r in {'push','void','cancelled','canceled'}:
        return 0.0
    if r not in {'win','won','loss','lost'}:
        return 0.0
    if r in {'loss','lost'}:
        return -1.0
    if odds is None or odds == 0:
        return 0.9091
    return odds / 100.0 if odds > 0 else 100.0 / abs(odds)


def load_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not DB.exists():
        return [], {'database_exists': False, 'reason': 'warehouse database missing'}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    tables = existing_tables(conn)
    rows: list[dict[str, Any]] = []
    sources: list[str] = []

    # Preferred source: explicit historical model/edge predictions already graded.
    for table in ['historical_edge_predictions','edge_predictions','daily_edge_history','prediction_history','player_prop_grades','grades']:
        if table not in tables:
            continue
        cols = table_columns(conn, table)
        result_col = pick(cols, 'result','grade','outcome','status')
        if not result_col:
            continue
        score_col = pick(cols, 'edge_score','confidence_score','model_score','score')
        prob_col = pick(cols, 'predicted_probability','model_probability','probability','win_probability')
        market_col = pick(cols, 'market','market_key','stat','prop_type')
        book_col = pick(cols, 'sportsbook','book','bookmaker')
        odds_col = pick(cols, 'odds','price','american_odds')
        clv_col = pick(cols, 'clv','avg_clv','closing_line_value')
        roi_col = pick(cols, 'profit_units','units','profit','pnl')
        type_col = pick(cols, 'market_type','line_type','is_alternate')
        player_col = pick(cols, 'player','player_name')
        select = [result_col]
        aliases = [('result',result_col),('edge_score',score_col),('probability',prob_col),('market',market_col),('sportsbook',book_col),('odds',odds_col),('clv',clv_col),('profit_units',roi_col),('market_type',type_col),('player',player_col)]
        query_parts=[]
        for alias,col in aliases:
            query_parts.append(f'"{col}" AS "{alias}"' if col else f'NULL AS "{alias}"')
        try:
            raw = conn.execute(f'SELECT {", ".join(query_parts)} FROM {table}').fetchall()
        except Exception:
            continue
        for r in raw:
            d=dict(r)
            result=norm(d.get('result'))
            if result not in {'win','won','loss','lost','push','void','cancelled','canceled'}:
                continue
            score=num(d.get('edge_score'))
            prob=num(d.get('probability'))
            if prob is not None and prob > 1:
                prob /= 100.0
            if score is None and prob is not None:
                score=prob*100
            if prob is None and score is not None:
                prob=max(0.01,min(0.99,score/100.0))
            odds=num(d.get('odds'))
            units=num(d.get('profit_units'))
            if units is None:
                units=profit_units(result,odds)
            market_type=d.get('market_type')
            if isinstance(market_type,(int,float)):
                market_type='alternate' if market_type else 'standard'
            market_type=norm(market_type)
            if market_type not in {'alternate','standard'}:
                market_type='alternate' if 'alternate' in norm(d.get('market')) or 'alt' in norm(d.get('market')) else 'standard'
            rows.append({
                'source_table':table,'result':result,'won':1 if result in {'win','won'} else 0 if result in {'loss','lost'} else None,
                'edge_score':score,'probability':prob,'market':d.get('market') or 'unknown','sportsbook':d.get('sportsbook') or 'unknown',
                'odds':odds,'clv':num(d.get('clv')),'profit_units':units,'market_type':market_type,'player':d.get('player')
            })
        if raw:
            sources.append(table)
    conn.close()
    return rows, {'database_exists': True, 'tables_found': sorted(tables), 'source_tables_used': sources}


def band(score: float | None) -> str:
    if score is None: return 'unscored'
    lo=int(score//10)*10
    if lo < 50: return '<50'
    if lo >= 90: return '90+'
    return f'{lo}-{lo+9}'


def summarize(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups=defaultdict(list)
    for r in rows:
        groups[str(r.get(key) or 'unknown')].append(r)
    out=[]
    for label,items in groups.items():
        settled=[r for r in items if r['won'] is not None]
        if not settled: continue
        wins=sum(r['won'] for r in settled)
        units=sum(float(r.get('profit_units') or 0) for r in settled)
        probs=[r['probability'] for r in settled if r.get('probability') is not None]
        clvs=[r['clv'] for r in settled if r.get('clv') is not None]
        out.append({'group':label,'sample_size':len(settled),'wins':wins,'losses':len(settled)-wins,'hit_rate':round(wins/len(settled),4),'roi':round(units/len(settled),4),'units':round(units,3),'avg_probability':round(sum(probs)/len(probs),4) if probs else None,'avg_clv':round(sum(clvs)/len(clvs),4) if clvs else None})
    return sorted(out,key=lambda x:(x['sample_size'],x['group']),reverse=True)


def calibration_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored=[r for r in rows if r['won'] is not None and r.get('probability') is not None]
    if not scored:
        return {'sample_size':0,'brier_score':None,'expected_calibration_error':None,'status':'insufficient_data'}
    brier=sum((r['probability']-r['won'])**2 for r in scored)/len(scored)
    buckets=defaultdict(list)
    for r in scored:
        idx=min(9,int(r['probability']*10))
        buckets[idx].append(r)
    ece=0.0; curve=[]
    for idx,items in sorted(buckets.items()):
        avgp=sum(r['probability'] for r in items)/len(items); actual=sum(r['won'] for r in items)/len(items)
        ece += len(items)/len(scored)*abs(avgp-actual)
        curve.append({'probability_band':f'{idx*10}-{idx*10+9}%','sample_size':len(items),'avg_predicted_probability':round(avgp,4),'actual_hit_rate':round(actual,4),'gap':round(actual-avgp,4)})
    return {'sample_size':len(scored),'brier_score':round(brier,5),'expected_calibration_error':round(ece,5),'status':'ok','reliability_curve':curve}


def build() -> dict[str, Any]:
    rows,source=load_records()
    for r in rows:
        r['score_band']=band(r.get('edge_score'))
    settled=[r for r in rows if r['won'] is not None]
    report={
        'sprint':7,
        'phase':'historical-confidence-calibration',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'ok' if settled else 'insufficient_data',
        'source':source,
        'summary':{
            'records_loaded':len(rows),'settled_records':len(settled),'scored_records':sum(r.get('edge_score') is not None for r in settled),
            'overall_hit_rate':round(sum(r['won'] for r in settled)/len(settled),4) if settled else None,
            'overall_roi':round(sum(float(r.get('profit_units') or 0) for r in settled)/len(settled),4) if settled else None,
            'warning':'Calibration is trustworthy only when historical predictions were generated before outcomes and matched to final grades.'
        },
        'calibration_metrics':calibration_metrics(rows),
        'by_score_band':summarize(rows,'score_band'),
        'by_market':summarize(rows,'market'),
        'by_sportsbook':summarize(rows,'sportsbook'),
        'by_market_type':summarize(rows,'market_type'),
        'readiness':{
            'minimum_recommended_sample':500,
            'sample_ready':len(settled)>=500,
            'calibration_ready':sum(r.get('edge_score') is not None for r in settled)>=300,
            'next_action':'Use calibrated score bands to revise Sprint 6 thresholds only after sample and chronology checks pass.'
        }
    }
    for path in OUTS:
        path.parent.mkdir(parents=True,exist_ok=True)
        json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps({'status':report['status'],**report['summary'],'brier_score':report['calibration_metrics'].get('brier_score')},indent=2))
    return report


def main() -> None:
    argparse.ArgumentParser().parse_args()
    build()


if __name__=='__main__':
    main()
