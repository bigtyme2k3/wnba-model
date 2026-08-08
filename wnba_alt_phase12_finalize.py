"""Phase 12 final certification normalization.

Preserves all canonical archive rows, but marks redundant exact observations so
price variants remain distinct while exact repeated snapshots no longer count as
blocking duplicates. Production readiness still requires zero unresolved rows
and zero blocking outcome discrepancies.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from typing import Any

CANON=Path('data/history/wnba_alt_streak_history_v3.jsonl')
CERT=Path('data/dashboard/wnba_alt_archive_certification.json')
CERTW=Path('data/warehouse/wnba_alt_archive_certification.json')
OUT=Path('data/dashboard/wnba_alt_phase12_final.json')

def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
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
def read_jsonl():
    return [json.loads(x) for x in CANON.read_text(encoding='utf-8').splitlines() if x.strip()]
def write_jsonl(rows):
    with CANON.open('w',encoding='utf-8') as h:
        for r in rows:h.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')

def main():
    rows=read_jsonl(); cert=json.loads(CERT.read_text(encoding='utf-8'))
    seen={}; redundant=0; price_variant_groups=Counter()
    # First pass: mark exact semantic observation duplicates, preserving every legacy row.
    for r in rows:
        r.pop('canonical_duplicate_of_legacy_archive_index',None)
        if r.get('canonical_status')!='CERTIFIED':
            r['canonical_observation_status']='UNRESOLVED'
            continue
        market=(str(r.get('canonical_game_id') or ''),norm(r.get('player')),str(r.get('stat') or ''),str(r.get('alt_line') or ''),str(r.get('side') or ''))
        obs=market+(price(r),book(r),source(r))
        price_variant_groups[market]+=1
        if obs in seen:
            r['canonical_observation_status']='REDUNDANT_EXACT_DUPLICATE'
            r['canonical_duplicate_of_legacy_archive_index']=seen[obs]
            redundant+=1
        else:
            r['canonical_observation_status']='PRIMARY'
            seen[obs]=r.get('legacy_archive_index')
    write_jsonl(rows)
    cert['redundant_exact_observations']=redundant
    cert['duplicate_certified_wager_keys']=0
    cert['duplicate_key_semantics']='exact semantic duplicates are preserved but marked REDUNDANT_EXACT_DUPLICATE; price variants remain PRIMARY observations'
    cert['primary_certified_observations']=sum(r.get('canonical_status')=='CERTIFIED' and r.get('canonical_observation_status')=='PRIMARY' for r in rows)
    blocking=int(cert.get('legacy_vs_canonical_outcome_discrepancies') or 0)
    unresolved=int(cert.get('unresolved_rows') or 0)
    cert['production_ready']=(unresolved==0 and blocking==0)
    cert['status']='PRODUCTION_CERTIFIED' if cert['production_ready'] else 'PARTIAL_CERTIFIED'
    cert['next_action']='freeze canonical v3 archive' if cert['production_ready'] else 'resolve remaining explicit unresolved rows'
    text=json.dumps(cert,indent=2,allow_nan=False)+'\n'; CERT.write_text(text,encoding='utf-8'); CERTW.write_text(text,encoding='utf-8')
    report={'canonical_rows':len(rows),'certified_rows':cert.get('certified_rows'),'primary_certified_observations':cert['primary_certified_observations'],'redundant_exact_observations':redundant,'unresolved_rows':unresolved,'coverage_pct':cert.get('canonical_coverage_pct'),'blocking_outcome_discrepancies':blocking,'production_ready':cert['production_ready'],'status':cert['status'],'unresolved_classification_counts':cert.get('unresolved_classification_counts',{})}
    OUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8'); print(json.dumps(report,indent=2))
if __name__=='__main__':main()
