"""Phase 11 forensic audit before final production certification.

Non-destructive. Audits the three remaining blocker classes:
1) unresolved canonical rows,
2) legacy-vs-canonical outcome discrepancies,
3) duplicate certified wager keys.

It also classifies duplicate groups using sportsbook/source fields so we do not
collapse legitimate multi-book variants by mistake.
"""
from __future__ import annotations

import csv, json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CANON = Path('data/history/wnba_alt_streak_history_v3.jsonl')
CERT = Path('data/dashboard/wnba_alt_archive_certification.json')
UNRES = Path('data/dashboard/wnba_alt_archive_unresolved_v3.csv')
OUT = Path('data/dashboard/wnba_alt_phase11_forensic.json')
OUTCSV = Path('data/dashboard/wnba_alt_phase11_forensic_duplicates.csv')


def norm(v: Any) -> str:
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def read_jsonl(path: Path):
    rows=[]
    if not path.exists(): return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip(): rows.append(json.loads(line))
    return rows


def book_key(r: dict[str,Any]) -> str:
    # Prefer the actual selected/best book, then source sportsbook fields.
    for k in ('best_book','sportsbook','book','bookmaker','best_odds_book','source_book'):
        if r.get(k): return norm(r.get(k))
    books=r.get('books')
    if isinstance(books,list): return '|'.join(sorted(norm(x) for x in books if x))
    if books: return norm(books)
    return ''


def price_key(r: dict[str,Any]) -> str:
    for k in ('best_odds','odds','price','american_odds'):
        if r.get(k) not in (None,''): return str(r.get(k))
    return ''


def main():
    canon=read_jsonl(CANON)
    cert=json.loads(CERT.read_text(encoding='utf-8'))
    unresolved=list(csv.DictReader(UNRES.open(encoding='utf-8'))) if UNRES.exists() else []

    # Existing certification duplicate definition (intentionally reproduced).
    groups=defaultdict(list)
    for i,r in enumerate(canon):
        if r.get('canonical_status')!='CERTIFIED': continue
        key=(str(r.get('canonical_game_id') or ''),norm(r.get('player')),str(r.get('stat') or ''),str(r.get('alt_line') or ''),str(r.get('side') or ''))
        groups[key].append((i,r))

    dup_rows=[]; class_counts=Counter(); true_dup_excess=0; multibook_excess=0
    for key,items in groups.items():
        if len(items)<=1: continue
        variants={(book_key(r),price_key(r),norm(r.get('source') or r.get('canonical_actual_source'))) for _,r in items}
        exact_payloads=Counter(json.dumps(r,sort_keys=True,default=str) for _,r in items)
        if len(exact_payloads)==1:
            cls='EXACT_ROW_DUPLICATE'; true_dup_excess += len(items)-1
        elif len({book_key(r) for _,r in items})>1:
            cls='MULTI_BOOK_VARIANT'; multibook_excess += len(items)-1
        elif len({price_key(r) for _,r in items})>1:
            cls='SAME_MARKET_PRICE_VARIANT'
        else:
            cls='SAME_MARKET_DISTINCT_RECORDS'
        class_counts[cls]+=len(items)-1
        for idx,r in items:
            dup_rows.append({
                'classification':cls,'archive_index':idx,'game_id':key[0],'player':r.get('player'),'stat':r.get('stat'),'alt_line':r.get('alt_line'),'side':r.get('side'),
                'book':book_key(r),'price':price_key(r),'record_id':r.get('record_id'),'legacy_archive_index':r.get('legacy_archive_index')
            })

    # Unresolved and discrepancy breakdowns are preserved verbatim for the next repair pass.
    unresolved_counts=Counter(r.get('classification') for r in unresolved)
    discrepancies=cert.get('discrepancy_samples') or []
    discrepancy_games=Counter((str(r.get('game_id') or ''),str(r.get('date') or ''),str(r.get('game') or '')) for r in discrepancies)

    report={
        'canonical_rows':len(canon),
        'certified_rows':cert.get('certified_rows'),
        'unresolved_rows':len(unresolved),
        'coverage_pct':cert.get('canonical_coverage_pct'),
        'unresolved_classification_counts':dict(unresolved_counts),
        'outcome_discrepancies':len(discrepancies),
        'discrepancy_game_clusters':[{'game_id':k[0],'date':k[1],'game':k[2],'rows':v} for k,v in discrepancy_games.items()],
        'legacy_duplicate_excess':cert.get('duplicate_certified_wager_keys'),
        'duplicate_forensic_classification_counts':dict(class_counts),
        'true_exact_duplicate_excess':true_dup_excess,
        'multi_book_variant_excess':multibook_excess,
        'duplicate_group_count':sum(1 for v in groups.values() if len(v)>1),
        'duplicate_row_samples':dup_rows[:100],
        'safety_note':'No archive or warehouse records were modified by Phase 11 forensic audit.'
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    fields=['classification','archive_index','game_id','player','stat','alt_line','side','book','price','record_id','legacy_archive_index']
    with OUTCSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(dup_rows)
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
