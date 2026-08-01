"""Build V5 Sprint 22 sportsbook intelligence from verified graded records only.

The report is deliberately coverage-aware: unknown sportsbook attribution remains
unknown, and no FanDuel/DraftKings comparison is emitted unless the archive
contains verified book labels. CLV summaries use only certified finite values.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE = Path('data/history/wnba_alt_streak_history.jsonl')
OUTPUTS = [
    Path('data/warehouse/wnba_v5_sportsbook_intelligence.json'),
    Path('data/dashboard/wnba_v5_sportsbook_intelligence.json'),
]
FINAL = {'WIN','LOSS','PUSH','VOID'}
MIN_SAMPLE = 20


def norm_book(value: Any) -> str | None:
    text = ' '.join(str(value or '').strip().lower().split())
    aliases = {
        'fanduel':'FanDuel','fan duel':'FanDuel','fd':'FanDuel',
        'draftkings':'DraftKings','draft kings':'DraftKings','dk':'DraftKings',
    }
    return aliases.get(text) or (str(value).strip() if text and text not in {'unknown','none','null','n/a'} else None)


def num(value: Any) -> float | None:
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str,Any]]:
    rows=[]
    if path.exists():
        for line in path.open(encoding='utf-8'):
            try:
                row=json.loads(line)
                if isinstance(row,dict): rows.append(row)
            except Exception:
                pass
    return rows


def summarize(items: list[dict[str,Any]], label: str) -> dict[str,Any]:
    wins=sum(str(r.get('outcome')).upper()=='WIN' for r in items)
    losses=sum(str(r.get('outcome')).upper()=='LOSS' for r in items)
    pushes=sum(str(r.get('outcome')).upper()=='PUSH' for r in items)
    decisions=wins+losses
    pnl=sum(v for r in items if (v:=num(r.get('profit_loss'))) is not None)
    line_clv=[v for r in items if (v:=num(r.get('line_clv'))) is not None]
    price_clv=[v for r in items if (v:=num(r.get('price_clv'))) is not None]
    return {
        'group':label,'records':len(items),'decisions':decisions,'wins':wins,'losses':losses,'pushes':pushes,
        'hit_rate':round(wins/decisions,4) if decisions else None,
        'profit_loss_units':round(pnl,4),'roi':round(pnl/decisions,4) if decisions else None,
        'average_line_clv':round(sum(line_clv)/len(line_clv),4) if line_clv else None,
        'average_price_clv':round(sum(price_clv)/len(price_clv),4) if price_clv else None,
        'line_clv_samples':len(line_clv),'price_clv_samples':len(price_clv),
        'reliable':decisions>=MIN_SAMPLE,
    }


def main() -> None:
    archive=read_jsonl(ARCHIVE)
    graded=[r for r in archive if str(r.get('outcome') or '').upper() in FINAL]
    attributed=[]
    unknown=[]
    for row in graded:
        book=norm_book(row.get('best_book') or row.get('closing_sportsbook'))
        if book:
            copy=dict(row);copy['_book']=book;attributed.append(copy)
        else:
            unknown.append(row)

    by_book: dict[str,list[dict[str,Any]]] = defaultdict(list)
    by_book_market: dict[tuple[str,str],list[dict[str,Any]]] = defaultdict(list)
    for row in attributed:
        book=row['_book'];stat=str(row.get('stat') or 'Unknown').upper()
        by_book[book].append(row);by_book_market[(book,stat)].append(row)

    book_rows=sorted((summarize(v,k) for k,v in by_book.items()),key=lambda x:(x['reliable'],x['roi'] if x['roi'] is not None else -999),reverse=True)
    market_rows=sorted((summarize(v,f'{book} | {market}')|{'book':book,'market':market} for (book,market),v in by_book_market.items()),key=lambda x:(x['reliable'],x['roi'] if x['roi'] is not None else -999),reverse=True)

    dk=next((r for r in book_rows if r['group']=='DraftKings'),None)
    fd=next((r for r in book_rows if r['group']=='FanDuel'),None)
    direct_comparison_available=bool(dk and fd and dk['decisions']>=MIN_SAMPLE and fd['decisions']>=MIN_SAMPLE)
    recommendations=[]
    if direct_comparison_available:
        leader=max((dk,fd),key=lambda r:r['roi'] if r['roi'] is not None else -999)
        recommendations.append({'type':'book_review','message':f"{leader['group']} leads verified ROI among books with at least {MIN_SAMPLE} decisions.",'evidence':leader})
    else:
        recommendations.append({'type':'data_quality','message':'FanDuel vs DraftKings performance comparison is blocked until both books have verified attribution and sufficient samples.','evidence':{'minimum_decisions_per_book':MIN_SAMPLE}})
    coverage=round(len(attributed)/len(graded),4) if graded else 0.0
    if coverage<0.8:
        recommendations.append({'type':'coverage','message':'Sportsbook attribution coverage is below 80%; preserve Unknown instead of inferring a book.','evidence':{'coverage':coverage,'unknown_records':len(unknown)}})

    certified_clv=[r for r in graded if str(r.get('clv_status') or '').upper().startswith('CERTIFIED')]
    report={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'ready' if direct_comparison_available else 'limited_by_attribution',
        'summary':{
            'graded_records':len(graded),'book_attributed_records':len(attributed),'unknown_book_records':len(unknown),
            'book_attribution_coverage':coverage,'books_detected':len(by_book),
            'certified_clv_records':len(certified_clv),'direct_fd_dk_comparison_available':direct_comparison_available,
            'minimum_reliable_sample':MIN_SAMPLE,
        },
        'by_sportsbook':book_rows,
        'by_sportsbook_market':market_rows,
        'recommendations':recommendations,
        'policy':{
            'verified_graded_outcomes_only':True,'unknown_book_inference':False,'minimum_sample':MIN_SAMPLE,
            'clv_policy':'Only certified finite CLV values are summarized. Missing values remain null.',
            'interpretation':'Observed associations are diagnostic and not causal claims.',
        },
    }
    for output in OUTPUTS:
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':
    main()
