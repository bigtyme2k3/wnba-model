"""Sprint 20 Phase 2: rank WNBA betting opportunities using edge, price, confidence, and CLV."""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

SHOP=Path('data/warehouse/market_intelligence.json')
EDGES=Path('data/history/wnba_edge_database.jsonl')
HISTORY=Path('data/history/wnba_opportunity_ranking_history.jsonl')
OUTS=[Path('data/warehouse/wnba_opportunity_rankings.json'),Path('data/dashboard/wnba_opportunity_rankings.json')]

WEIGHTS={'expected_value':0.35,'probability_edge':0.20,'confidence':0.15,'clv':0.15,'line_shopping':0.10,'market_depth':0.05}

def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def read_json(path,default):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def read_jsonl(path):
    out=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out

def write_jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')

def key(date_value,player,game,market,side):
    return '|'.join(norm(v) for v in (date_value,player,game,market,side))

def clamp(x,lo=0.0,hi=1.0):return max(lo,min(hi,x))

def component_scores(edge,shop):
    ev=num(edge.get('expected_value'));prob_edge=num(edge.get('probability_edge'));confidence=num(edge.get('confidence'))
    clv=num(edge.get('clv'));price=num(shop.get('price_advantage'));books=num(shop.get('book_count')) or 0
    if confidence is not None and confidence>1:confidence/=100
    return {
        'expected_value':None if ev is None else clamp((ev+0.05)/0.25),
        'probability_edge':None if prob_edge is None else clamp((prob_edge+0.02)/0.15),
        'confidence':None if confidence is None else clamp((confidence-0.50)/0.40),
        'clv':None if clv is None else clamp((clv+0.5)/2.0),
        'line_shopping':None if price is None else clamp((price+0.01)/0.08),
        'market_depth':clamp(books/3.0),
    }

def weighted_score(components):
    active={k:v for k,v in components.items() if v is not None}
    total=sum(WEIGHTS[k] for k in active)
    return 0.0 if not total else 100*sum(WEIGHTS[k]*v for k,v in active.items())/total

def tier(score,ev,eligible):
    if not eligible or ev is None or ev<=0:return 'PASS'
    if score>=80 and ev>=0.08:return 'A'
    if score>=68 and ev>=0.04:return 'B'
    if score>=55:return 'C'
    return 'PASS'

def build(target):
    now=datetime.now(timezone.utc).isoformat();shopping=read_json(SHOP,{'markets':[]});edges=read_jsonl(EDGES)
    shop_index={key(r.get('date'),r.get('player'),r.get('game'),r.get('market'),r.get('side')):r for r in shopping.get('markets',[])}
    edge_index=defaultdict(list)
    for edge in edges:
        edge_index[key(edge.get('date'),edge.get('player'),edge.get('game'),edge.get('market'),edge.get('selection'))].append(edge)
    ranked=[];unmatched=0
    for sk,shop in shop_index.items():
        candidates=edge_index.get(sk,[])
        if not candidates:unmatched+=1;continue
        edge=max(candidates,key=lambda r:num(r.get('expected_value')) if num(r.get('expected_value')) is not None else -999)
        components=component_scores(edge,shop);score=round(weighted_score(components),2);ev=num(edge.get('expected_value'))
        eligible=bool(edge.get('eligible_for_bet')) or str(edge.get('recommendation') or '').upper() in {'BET','PLAY','STRONG BET'}
        grade=tier(score,ev,eligible)
        ranked.append({
            'ranking_key':sk,'date':target,'generated_at_utc':now,'player':shop.get('player'),'game':shop.get('game'),'market':shop.get('market'),'side':shop.get('side'),
            'best_book':shop.get('best_book'),'best_line':shop.get('best_line'),'best_odds':shop.get('best_odds'),'book_count':shop.get('book_count'),
            'model_projection':edge.get('model_projection'),'model_probability':edge.get('model_probability'),'implied_probability':edge.get('implied_probability'),
            'probability_edge':edge.get('probability_edge'),'expected_value':ev,'expected_value_pct':None if ev is None else round(ev*100,2),'confidence':edge.get('confidence'),
            'clv':edge.get('clv'),'clv_grade':edge.get('clv_grade'),'price_advantage':shop.get('price_advantage'),'market_disagreement_score':shop.get('market_disagreement_score'),
            'opportunity_score':score,'tier':grade,'eligible_for_bet':eligible,'recommendation':'BET' if grade in {'A','B'} else 'LEAN' if grade=='C' else 'PASS',
            'components':{k:(None if v is None else round(v*100,2)) for k,v in components.items()},'source_edge_key':edge.get('edge_key')})
    ranked.sort(key=lambda r:(r['opportunity_score'],r.get('expected_value') or -999),reverse=True)
    for i,row in enumerate(ranked,1):row['rank']=i
    existing={r.get('ranking_key'):r for r in read_jsonl(HISTORY) if r.get('ranking_key')};inserted=updated=0
    for row in ranked:
        prior=existing.get(row['ranking_key']);material=lambda x:{k:v for k,v in x.items() if k not in {'generated_at_utc','rank'}}
        if prior is None:existing[row['ranking_key']]=row;inserted+=1
        elif material(prior)!=material(row):existing[row['ranking_key']]=row;updated+=1
    write_jsonl(HISTORY,sorted(existing.values(),key=lambda r:(str(r.get('date')),str(r.get('ranking_key')))))
    report={'generated_at_utc':now,'target_date':target,'methodology':{'weights':WEIGHTS,'missing_components':'weights are redistributed across available components','score_range':'0-100'},
        'summary':{'ranked_opportunities':len(ranked),'a_tier':sum(r['tier']=='A' for r in ranked),'b_tier':sum(r['tier']=='B' for r in ranked),'c_tier':sum(r['tier']=='C' for r in ranked),'pass':sum(r['tier']=='PASS' for r in ranked),'unmatched_line_shopping_records':unmatched,'inserted_history_records':inserted,'updated_history_records':updated},
        'top_opportunities':ranked[:50],'all_ranked':ranked[:500]}
    for path in OUTS:path.parent.mkdir(parents=True,exist_ok=True);json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Opportunity rankings:',build(a.date)['summary'])
if __name__=='__main__':main()
