"""WNBA V5 Operations Sprint 3 M04 - explicit CLV evidence engine.

Joins immutable forward V5 predictions to only S3-M02 observations that were
captured explicitly before tip. No historical/latest/inferred price is accepted
as a closing line.

Outputs:
  data/dashboard/wnba_v5_explicit_clv.csv
  data/dashboard/wnba_v5_clv_summary.json
  data/dashboard/wnba_v5_market_edge.json
  data/dashboard/wnba_v5_s3_m04_report.json
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

DASH = Path('data/dashboard')
HIST = Path('data/history')
LEDGER = HIST / 'wnba_v5_forward_predictions.jsonl'
CLOSES = DASH / 'wnba_v5_closing_lines.csv'
OUT_CSV = DASH / 'wnba_v5_explicit_clv.csv'
SUMMARY = DASH / 'wnba_v5_clv_summary.json'
MARKET_EDGE = DASH / 'wnba_v5_market_edge.json'
REPORT = DASH / 'wnba_v5_s3_m04_report.json'

FIELDS = [
    'prediction_id','ranking_key','prediction_generated_at_utc','date','game','player','stat','side',
    'issued_line','issued_odds','issued_book','issued_implied_probability','v5_probability',
    'close_snapshot_id','close_captured_at_utc','close_minutes_to_tip','close_line','close_odds',
    'close_book','close_book_key','close_market_key','close_implied_probability',
    'line_clv','price_clv_probability','market_probability_shift','v5_edge_at_close',
    'same_book_close','same_line_close','clv_evidence_class','outcome','actual'
]


def f(v, default=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def implied(o):
    o=f(o)
    if o is None or o == 0:
        return None
    return abs(o)/(abs(o)+100.0) if o < 0 else 100.0/(o+100.0)


def read_ledger():
    if not LEDGER.exists():
        return []
    out=[]
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try: out.append(json.loads(line))
            except Exception: pass
    return out


def read_closes():
    if not CLOSES.exists():
        return []
    try:
        rows=list(csv.DictReader(CLOSES.open(encoding='utf-8-sig',newline='')))
    except Exception:
        return []
    out=[]
    for r in rows:
        explicit=str(r.get('is_explicit_close') or '').strip().lower() in {'true','1','yes'}
        mins=f(r.get('minutes_to_tip'))
        if not explicit or r.get('capture_class') != 'EXPLICIT_PRETIP_CLOSE':
            continue
        if mins is None or mins < 0:
            continue
        out.append(r)
    return out


def game_key(v):
    x=norm(v).replace(' vs. ',' @ ').replace(' vs ',' @ ')
    teams=sorted(p.strip() for p in x.split('@') if p.strip())
    return '|'.join(teams)


def exact_match(pred, close):
    return (
        game_key(pred.get('game')) == game_key(close.get('game')) and
        norm(pred.get('player')) == norm(close.get('player')) and
        str(pred.get('stat') or '').upper() == str(close.get('stat') or '').upper() and
        str(pred.get('side') or '').upper() == str(close.get('side') or '').upper()
    )


def choose_close(pred, candidates):
    """Prefer same sportsbook, then the observation nearest tip (smallest minutes)."""
    if not candidates:
        return None
    issued_book=norm(pred.get('book'))
    def rank(r):
        same = 0 if issued_book and issued_book in {norm(r.get('sportsbook')),norm(r.get('sportsbook_key'))} else 1
        mins=f(r.get('minutes_to_tip'), 999999.0)
        return (same, mins, str(r.get('captured_at_utc') or ''))
    return sorted(candidates,key=rank)[0]


def r6(v):
    return None if v is None else round(v,6)


def main():
    now=datetime.now(timezone.utc).isoformat()
    preds=read_ledger(); closes=read_closes()
    evidence=[]; missing=[]

    for p in preds:
        matches=[c for c in closes if exact_match(p,c)]
        c=choose_close(p,matches)
        if c is None:
            missing.append({
                'prediction_id':p.get('prediction_id'),'date':p.get('date'),'game':p.get('game'),
                'player':p.get('player'),'stat':p.get('stat'),'side':p.get('side'),
                'issued_book':p.get('book'),'reason':'NO_EXPLICIT_PRETIP_CLOSE_MATCH'
            })
            continue

        il=f(p.get('line')); io=f(p.get('odds')); cl=f(c.get('point')); co=f(c.get('price'))
        ip=implied(io); cp=implied(co); vp=f(p.get('v5_probability'))
        side=str(p.get('side') or '').upper()
        line_clv=None
        if il is not None and cl is not None:
            # Positive means the issued threshold became more favorable by close.
            line_clv=(cl-il) if side=='OVER' else ((il-cl) if side=='UNDER' else None)
        price_clv=(cp-ip) if cp is not None and ip is not None else None
        v5_edge=(vp-cp) if vp is not None and cp is not None else None
        same_book=norm(p.get('book')) in {norm(c.get('sportsbook')),norm(c.get('sportsbook_key'))} if p.get('book') else False
        same_line=(il is not None and cl is not None and abs(il-cl)<1e-9)
        evidence_class='EXPLICIT_SAME_BOOK_CLOSE' if same_book else 'EXPLICIT_MARKET_CLOSE'

        evidence.append({
            'prediction_id':p.get('prediction_id'),'ranking_key':p.get('ranking_key'),
            'prediction_generated_at_utc':p.get('prediction_generated_at_utc'),'date':p.get('date'),
            'game':p.get('game'),'player':p.get('player'),'stat':p.get('stat'),'side':side,
            'issued_line':il,'issued_odds':io,'issued_book':p.get('book'),
            'issued_implied_probability':r6(ip),'v5_probability':vp,
            'close_snapshot_id':c.get('snapshot_id'),'close_captured_at_utc':c.get('captured_at_utc'),
            'close_minutes_to_tip':f(c.get('minutes_to_tip')),'close_line':cl,'close_odds':co,
            'close_book':c.get('sportsbook'),'close_book_key':c.get('sportsbook_key'),
            'close_market_key':c.get('market_key'),'close_implied_probability':r6(cp),
            'line_clv':r6(line_clv),'price_clv_probability':r6(price_clv),
            'market_probability_shift':r6(price_clv),'v5_edge_at_close':r6(v5_edge),
            'same_book_close':same_book,'same_line_close':same_line,
            'clv_evidence_class':evidence_class,'outcome':p.get('outcome'),'actual':p.get('actual')
        })

    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=FIELDS);w.writeheader();w.writerows([{k:r.get(k) for k in FIELDS} for r in evidence])

    total=len(preds); covered=len(evidence); coverage=(100.0*covered/total) if total else 0.0
    line_vals=[f(r.get('line_clv')) for r in evidence if f(r.get('line_clv')) is not None]
    price_vals=[f(r.get('price_clv_probability')) for r in evidence if f(r.get('price_clv_probability')) is not None]
    close_edges=[f(r.get('v5_edge_at_close')) for r in evidence if f(r.get('v5_edge_at_close')) is not None]
    positive_line=sum(x>0 for x in line_vals); positive_price=sum(x>0 for x in price_vals)

    summary={
        'version':'V5','sprint':'OPERATIONS_SPRINT_3','module':'S3-M04',
        'stage':'EXPLICIT_CLV_ENGINE','generated_at_utc':now,
        'status':'READY' if total else 'WAITING_FOR_FORWARD_PREDICTIONS',
        'forward_predictions':total,'explicit_close_predictions':covered,
        'missing_explicit_close_predictions':len(missing),'explicit_clv_coverage_pct':round(coverage,2),
        'minimum_promotion_clv_coverage_pct':60.0,
        'same_book_close_rows':sum(bool(r.get('same_book_close')) for r in evidence),
        'same_line_close_rows':sum(bool(r.get('same_line_close')) for r in evidence),
        'avg_line_clv':r6(mean(line_vals)) if line_vals else None,
        'positive_line_clv_pct':round(100.0*positive_line/len(line_vals),2) if line_vals else None,
        'avg_price_clv_probability':r6(mean(price_vals)) if price_vals else None,
        'positive_price_clv_pct':round(100.0*positive_price/len(price_vals),2) if price_vals else None,
        'avg_v5_edge_at_close':r6(mean(close_edges)) if close_edges else None,
        'evidence_classes':dict(Counter(r.get('clv_evidence_class') for r in evidence)),
        'policy':'Only S3-M02 EXPLICIT_PRETIP_CLOSE observations count toward coverage. Missing closes remain missing; no latest, post-tip, or inferred price is substituted.',
        'next_module':'S3-M05 Evidence Accumulation Dashboard'
    }
    market_edge={
        'generated_at_utc':now,
        'explicit_close_predictions':covered,
        'explicit_clv_coverage_pct':round(coverage,2),
        'average_v5_edge_at_close':summary['avg_v5_edge_at_close'],
        'average_price_clv_probability':summary['avg_price_clv_probability'],
        'average_line_clv':summary['avg_line_clv'],
        'missing_predictions':missing[:100],
        'rows':evidence
    }
    report=dict(summary)
    report['production_ready']=False
    report['research_only']=True

    SUMMARY.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    MARKET_EDGE.write_text(json.dumps(market_edge,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
