"""V5-M06 Market Movement Intelligence.

Research-only market behavior layer. Links V5-M05 walk-forward predictions to
repository line snapshots without inventing missing closes. When no explicit
closing stage exists, the latest chronological snapshot is retained as an
INFERRED_LATEST reference and never labeled a true close.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

PRED=Path('data/dashboard/wnba_v5_m05_predictions.csv')
SNAPS=Path('data/history/wnba_line_snapshots.jsonl')
OUT_MARKET=Path('data/dashboard/wnba_v5_market_movement.csv')
OUT_CLV=Path('data/dashboard/wnba_v5_clv_features.csv')
OUT_STEAM=Path('data/dashboard/wnba_v5_steam_alerts.json')
OUT_STATE=Path('data/dashboard/wnba_v5_market_state.json')
OUT_BOOK=Path('data/dashboard/wnba_v5_book_behavior.json')
OUT_REPORT=Path('data/dashboard/wnba_v5_m06_report.json')


def f(v, default=None):
    try:
        x=float(v); return x if math.isfinite(x) else default
    except Exception: return default

def norm(v): return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def side_norm(v):
    s=norm(v).upper()
    if s in {'YES'}: return 'OVER'
    if s in {'NO'}: return 'UNDER'
    return s

def implied(odds):
    o=f(odds)
    if o is None or o==0:return None
    return abs(o)/(abs(o)+100.0) if o<0 else 100.0/(o+100.0)
def price(row,side):
    s=side_norm(side)
    if s=='OVER': return f(row.get('over_price'),f(row.get('price'),f(row.get('odds'))))
    if s=='UNDER': return f(row.get('under_price'),f(row.get('price'),f(row.get('odds'))))
    return f(row.get('price'),f(row.get('odds')))
def ts(row): return str(row.get('captured_at_utc') or row.get('timestamp') or row.get('captured_at') or '')
def parse_ts(v):
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00'))
    except Exception:return None

def read_jsonl(path):
    rows=[]
    if not path.exists():return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            r=json.loads(line)
            if isinstance(r,dict):rows.append(r)
        except Exception:pass
    return rows

def pred_key(r): return (str(r.get('game_date') or r.get('date') or ''),norm(r.get('player')),norm(r.get('stat') or r.get('market')),side_norm(r.get('side') or r.get('signal')))
def snap_key(r): return (str(r.get('date') or ''),norm(r.get('player')),norm(r.get('stat') or r.get('market')),side_norm(r.get('signal') or r.get('side')))
def line_direction(open_line, later_line, side):
    a,b=f(open_line),f(later_line)
    if a is None or b is None:return None
    return b-a if side_norm(side)=='OVER' else a-b

def price_direction(open_odds,later_odds):
    a,b=implied(open_odds),implied(later_odds)
    if a is None or b is None:return None
    return b-a

def movement_class(line_move, price_move, books, n, span_min, explicit_close):
    lm=abs(line_move or 0); pm=abs(price_move or 0)
    if n<=1 or (lm<0.25 and pm<0.015): return 'STABLE'
    if lm>=1.0 and books>=2 and (span_min is None or span_min<=180): return 'STEAM'
    if lm>=1.0 or pm>=0.06:return 'SHARP_MOVE'
    if n>=3 and (lm>=0.5 or pm>=0.03):return 'GRADUAL_MOVE'
    if not explicit_close:return 'INCOMPLETE_TIMELINE'
    return 'MINOR_MOVE'

def main():
    if not PRED.exists(): raise SystemExit('M06_INPUT_MISSING: M05 predictions')
    preds=list(csv.DictReader(PRED.open(encoding='utf-8-sig',newline='')))
    snaps=read_jsonl(SNAPS)
    by=defaultdict(list)
    for s in snaps: by[snap_key(s)].append(s)
    for k in by: by[k].sort(key=ts)

    rows=[]; book_first=Counter(); book_moves=defaultdict(list); steam=[]
    for p in preds:
        opts=by.get(pred_key(p),[])
        if not opts:
            rows.append({**p,'snapshot_count':0,'book_count':0,'opening_line':None,'latest_line':None,'reference_close_line':None,'close_quality':'UNAVAILABLE','line_move':None,'price_move':None,'movement_class':'NO_SNAPSHOT_MATCH','steam_detected':False,'reverse_move_vs_knn':False,'first_moving_book':None})
            continue
        explicit_open=next((x for x in opts if norm(x.get('stage')) in {'open','opening'}),None)
        explicit_close=next((x for x in reversed(opts) if norm(x.get('stage')) in {'close','closing'}),None)
        opening=explicit_open or opts[0]; latest=opts[-1]; close_ref=explicit_close or latest
        side=p.get('side'); ol=f(opening.get('line')); ll=f(latest.get('line')); cl=f(close_ref.get('line'))
        oo=price(opening,side); lo=price(latest,side); co=price(close_ref,side)
        lm=line_direction(ol,ll,side); pm=price_direction(oo,lo)
        books=sorted({str(x.get('book') or x.get('source') or '').strip() for x in opts if x.get('book') or x.get('source')})
        t0=parse_ts(ts(opening)); t1=parse_ts(ts(latest)); span=((t1-t0).total_seconds()/60) if t0 and t1 else None
        cls=movement_class(lm,pm,len(books),len(opts),span,explicit_close is not None)
        is_steam=cls=='STEAM'
        # KNN signal: market moving toward predicted side if KNN > .5, against if < .5.
        kp=f(p.get('knn_probability')); knn_side=side_norm(side) if kp is not None and kp>=0.5 else ('UNDER' if side_norm(side)=='OVER' else 'OVER')
        move_toward_selected=(lm or 0)>0 or (pm or 0)>0
        reverse=bool(kp is not None and ((kp>=0.5 and not move_toward_selected and (abs(lm or 0)>=0.5 or abs(pm or 0)>=0.03)) or (kp<0.5 and move_toward_selected and (abs(lm or 0)>=0.5 or abs(pm or 0)>=0.03))))
        first_book=None
        for a,b in zip(opts,opts[1:]):
            dl=line_direction(a.get('line'),b.get('line'),side); dp=price_direction(price(a,side),price(b,side))
            if abs(dl or 0)>=0.25 or abs(dp or 0)>=0.015:
                first_book=str(b.get('book') or b.get('source') or '') or None; break
        if first_book: book_first[first_book]+=1
        for book in books: book_moves[book].append((lm or 0,pm or 0,is_steam))
        rec={**p,'snapshot_count':len(opts),'book_count':len(books),'books':'|'.join(books),'opening_line':ol,'opening_odds':oo,'latest_line':ll,'latest_odds':lo,'reference_close_line':cl,'reference_close_odds':co,'close_quality':'EXPLICIT_CLOSE' if explicit_close else 'INFERRED_LATEST','line_move':lm,'price_move':pm,'elapsed_minutes':round(span,2) if span is not None else None,'movement_class':cls,'steam_detected':is_steam,'reverse_move_vs_knn':reverse,'first_moving_book':first_book,'knn_implied_side':knn_side}
        rows.append(rec)
        if is_steam: steam.append(rec)

    matched=[r for r in rows if r['snapshot_count']>0]
    explicit=[r for r in matched if r['close_quality']=='EXPLICIT_CLOSE']
    inferred=[r for r in matched if r['close_quality']=='INFERRED_LATEST']
    classes=Counter(r['movement_class'] for r in rows)
    book_report={}
    for book,vals in sorted(book_moves.items()):
        if not vals:continue
        book_report[book]={'markets_observed':len(vals),'first_move_count':book_first.get(book,0),'avg_directional_line_move':round(sum(x[0] for x in vals)/len(vals),4),'avg_price_probability_move':round(sum(x[1] for x in vals)/len(vals),5),'steam_involvement':sum(1 for x in vals if x[2])}

    state={
      'version':'V5','module':'V5-M06','stage':'MARKET_MOVEMENT_INTELLIGENCE','status':'READY',
      'prediction_rows':len(rows),'snapshot_rows_total':len(snaps),'matched_prediction_rows':len(matched),
      'snapshot_match_coverage_pct':round(100*len(matched)/len(rows),2) if rows else 0.0,
      'explicit_close_rows':len(explicit),'explicit_clv_coverage_pct':round(100*len(explicit)/len(rows),2) if rows else 0.0,
      'inferred_latest_rows':len(inferred),'movement_class_counts':dict(classes),'steam_alerts':len(steam),
      'reverse_moves_vs_knn':sum(bool(r.get('reverse_move_vs_knn')) for r in matched),
      'research_only':True,'production_note':'Only EXPLICIT_CLOSE rows may count toward the M05 CLV promotion gate.',
      'next_module':'V5-M07 Context + Player Similarity Intelligence'
    }
    report={**state,'book_behavior':book_report,'top_first_movers':book_first.most_common(10),'methodology':{'explicit_close':'stage close/closing only','inferred_latest':'latest snapshot, never promoted as true close','steam':'multi-book + >=1.0 directional line move within <=180 minutes','reverse_move':'material market move against KNN implied direction'}}

    OUT_MARKET.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0].keys()) if rows else []
    with OUT_MARKET.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    clv_fields=['archive_index','game_date','game_id','player','stat','side','alt_line','american_odds','reference_close_line','reference_close_odds','close_quality','line_move','price_move','snapshot_count','book_count']
    with OUT_CLV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=clv_fields); w.writeheader(); w.writerows([{k:r.get(k) for k in clv_fields} for r in rows])
    OUT_STEAM.write_text(json.dumps({'count':len(steam),'alerts':steam[:100]},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_STATE.write_text(json.dumps(state,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_BOOK.write_text(json.dumps({'books':book_report,'top_first_movers':book_first.most_common(10)},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(state,indent=2))

if __name__=='__main__': main()
