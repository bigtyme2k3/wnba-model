"""Phase 11 certification cleanup.

Non-destructive to legacy/canonical archive rows. This corrects certification semantics:
- price variants of the same market are observations, not duplicate wagers;
- only exact semantic observation duplicates are blocking duplicates;
- July 14 legacy/canonical discrepancies are checked against repository-local raw boxscores.
"""
from __future__ import annotations

import csv, json, math
from collections import Counter
from pathlib import Path
from typing import Any

from wnba_alt_performance_tracker import stat_value

CANON=Path('data/history/wnba_alt_streak_history_v3.jsonl')
CERT=Path('data/dashboard/wnba_alt_archive_certification.json')
CERTW=Path('data/warehouse/wnba_alt_archive_certification.json')
FORENSIC=Path('data/dashboard/wnba_alt_phase11_forensic.json')
RAW=Path('data/raw/boxscores_2026-07-14.csv')
OUT=Path('data/dashboard/wnba_alt_phase11_cleanup.json')

def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def num(v:Any):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def read_jsonl(p:Path):
    rows=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.strip(): rows.append(json.loads(line))
    return rows

def price(r):
    for k in ('best_odds','odds','price','american_odds'):
        if r.get(k) not in (None,''): return str(r.get(k))
    return ''

def book(r):
    for k in ('best_book','sportsbook','book','bookmaker','best_odds_book','source_book'):
        if r.get(k): return norm(r.get(k))
    b=r.get('books')
    if isinstance(b,list): return '|'.join(sorted(norm(x) for x in b if x))
    return norm(b)

def source(r): return norm(r.get('source') or r.get('canonical_actual_source'))

def raw_record(r):
    pts=num(r.get('pts'));reb=num(r.get('reb'));ast=num(r.get('ast'));stl=num(r.get('stl'));blk=num(r.get('blk'));tov=num(r.get('tov'));pf=num(r.get('pf'));three=num(r.get('threes') or r.get('three_pm') or r.get('3pm'))
    return {'scoring':{'total_pts':pts,'three_pm':three},'boxscore':{'reb':reb,'ast':ast,'stl':stl,'blk':blk,'tov':tov},'fouls':{'total_committed':pf},'derived':{'pra':None if None in (pts,reb,ast) else pts+reb+ast,'pr':None if None in (pts,reb) else pts+reb,'pa':None if None in (pts,ast) else pts+ast,'ra':None if None in (reb,ast) else reb+ast}}

def main():
    canon=read_jsonl(CANON)
    cert=json.loads(CERT.read_text(encoding='utf-8'))
    forensic=json.loads(FORENSIC.read_text(encoding='utf-8'))

    # Observation-level duplicate definition includes price/book/source. This preserves
    # legitimate repeated market snapshots while still catching identical observations.
    keys=Counter()
    for r in canon:
        if r.get('canonical_status')!='CERTIFIED': continue
        k=(str(r.get('canonical_game_id') or ''),norm(r.get('player')),str(r.get('stat') or ''),str(r.get('alt_line') or ''),str(r.get('side') or ''),price(r),book(r),source(r))
        keys[k]+=1
    exact_dup=sum(v-1 for v in keys.values() if v>1)

    # Validate the 9 discrepancy rows against the repository-local July 14 raw boxscore.
    raw=[]
    if RAW.exists():
        with RAW.open(encoding='utf-8-sig',newline='') as h: raw=list(csv.DictReader(h))
    by_gp={}
    for rr in raw:
        gid=str(rr.get('game_id') or rr.get('event_id') or '')
        p=norm(rr.get('player'))
        if gid and p: by_gp[(gid,p)]=rr

    confirmations=[]
    for d in cert.get('discrepancy_samples') or []:
        gid=str(d.get('game_id') or '')
        idx=int(d.get('archive_index'))
        c=canon[idx]
        rr=by_gp.get((gid,norm(d.get('player'))))
        rv=None if rr is None else stat_value(raw_record(rr),str(c.get('stat') or ''))
        ca=c.get('canonical_actual')
        ok=(rv is not None and ca is not None and abs(float(rv)-float(ca))<1e-9)
        confirmations.append({'archive_index':idx,'player':d.get('player'),'game_id':gid,'stat':c.get('stat'),'raw_actual':rv,'canonical_actual':ca,'raw_confirms_canonical':ok})

    confirmed=sum(x['raw_confirms_canonical'] for x in confirmations)
    blocking_discrepancies=(len(confirmations)-confirmed)

    cert['legacy_duplicate_market_excess']=forensic.get('legacy_duplicate_excess',0)
    cert['price_variant_observation_excess']=forensic.get('duplicate_forensic_classification_counts',{}).get('SAME_MARKET_PRICE_VARIANT',0)
    cert['duplicate_certified_wager_keys']=exact_dup
    cert['duplicate_key_semantics']='game+player+stat+line+side+price+book+source; price variants are not duplicate wagers'
    cert['legacy_vs_canonical_outcome_discrepancies']=blocking_discrepancies
    cert['legacy_outcome_errors_confirmed_by_local_raw']=confirmed
    cert['phase11_discrepancy_validation']=confirmations
    cert['production_ready']=(cert.get('unresolved_rows',0)==0 and blocking_discrepancies==0 and exact_dup==0)
    if cert.get('unresolved_rows',0): cert['status']='PARTIAL_CERTIFIED'
    elif cert['production_ready']: cert['status']='PRODUCTION_CERTIFIED'
    cert['next_action']='resolve remaining explicit unresolved rows' if cert.get('unresolved_rows',0) else 'freeze canonical v3 archive'

    text=json.dumps(cert,indent=2,allow_nan=False)+'\n'
    CERT.write_text(text,encoding='utf-8'); CERTW.write_text(text,encoding='utf-8')
    report={'certified_rows':cert.get('certified_rows'),'unresolved_rows':cert.get('unresolved_rows'),'coverage_pct':cert.get('canonical_coverage_pct'),'exact_observation_duplicate_excess':exact_dup,'price_variant_observation_excess':cert['price_variant_observation_excess'],'discrepancies_checked':len(confirmations),'legacy_errors_confirmed':confirmed,'blocking_outcome_discrepancies':blocking_discrepancies,'production_ready':cert['production_ready'],'status':cert['status']}
    OUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
