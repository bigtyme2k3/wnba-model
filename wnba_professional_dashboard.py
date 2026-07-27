"""Sprint 20 Phase 5: aggregate WNBA market intelligence into one dashboard payload."""
from __future__ import annotations
import argparse,json,math
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path

SOURCES={
'opportunities':Path('data/dashboard/opportunity_finder.json'),
'movement':Path('data/dashboard/market_movement.json'),
'shopping':Path('data/dashboard/market_intelligence.json'),
'rankings':Path('data/dashboard/wnba_opportunity_rankings.json'),
'clv':Path('data/dashboard/wnba_clv_summary.json')}
HIST=Path('data/history/opportunity_finder_history.jsonl')
OUTS=[Path('data/warehouse/professional_dashboard.json'),Path('data/dashboard/professional_dashboard.json'),Path('docs/data/professional_dashboard.json')]

def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

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

def build(target):
    now=datetime.now(timezone.utc).isoformat();src={k:read_json(v,{}) for k,v in SOURCES.items()}
    opp=src['opportunities'];move=src['movement'];shop=src['shopping'];rank=src['rankings'];clv=src['clv']
    rows=[r for r in opp.get('all_opportunities',[]) if str(r.get('date'))==target]
    history=[r for r in read_jsonl(HIST) if str(r.get('date'))==target]
    books=Counter(r.get('best_book') for r in rows if r.get('best_book'))
    markets=Counter(str(r.get('market') or 'UNKNOWN') for r in rows)
    recs=Counter(str(r.get('recommendation') or 'PASS') for r in rows)
    evs=[num(r.get('expected_value')) for r in rows if num(r.get('expected_value')) is not None]
    scores=[num(r.get('opportunity_index')) for r in rows if num(r.get('opportunity_index')) is not None]
    actionable=[r for r in rows if r.get('actionable')]
    alerts=[]
    for r in opp.get('arbitrage',[])[:25]: alerts.append({'type':'ARBITRAGE','severity':'HIGH','title':f"{r.get('player') or r.get('game')} {r.get('market')}",'detail':f"{r.get('over_book')} {r.get('over_odds')} / {r.get('under_book')} {r.get('under_odds')}",'edge_pct':r.get('arb_edge_pct')})
    for r in move.get('top_steam_alerts',[])[:25]: alerts.append({'type':'STEAM','severity':'MEDIUM','title':f"{r.get('player') or r.get('game')} {r.get('market')} {r.get('side')}",'detail':f"Move {r.get('total_directional_line_move')} across {r.get('book_count')} books",'score':r.get('steam_score')})
    for r in move.get('reverse_line_movements',[])[:25]: alerts.append({'type':'REVERSE_MOVE','severity':'MEDIUM','title':f"{r.get('player') or r.get('game')} {r.get('market')} {r.get('side')}",'detail':r.get('model_market_classification'),'score':r.get('market_confidence_score')})
    health={k:{'path':str(SOURCES[k]),'available':bool(src[k]),'target_date':src[k].get('target_date'),'generated_at_utc':src[k].get('generated_at_utc')} for k in SOURCES}
    report={
      'generated_at_utc':now,'target_date':target,'dashboard_version':'Sprint 20 Phase 5',
      'executive_summary':{
        'scanned_opportunities':len(rows),'actionable_opportunities':len(actionable),'strong_bets':recs['STRONG BET'],'bets':recs['BET'],'leans':recs['LEAN'],'passes':recs['PASS'],
        'average_expected_value_pct':round(100*sum(evs)/len(evs),2) if evs else None,'average_opportunity_index':round(sum(scores)/len(scores),2) if scores else None,
        'arbitrage_opportunities':len(opp.get('arbitrage',[])),'middle_opportunities':len(opp.get('middles',[])),'market_inefficiencies':len(opp.get('market_inefficiencies',[])),
        'steam_alerts':move.get('summary',{}).get('steam_alerts',0),'reverse_line_movements':move.get('summary',{}).get('reverse_line_movements',0),
        'tracked_markets':move.get('summary',{}).get('tracked_markets',0),'line_shopping_markets':shop.get('summary',{}).get('markets',0),'ranked_opportunities':rank.get('summary',{}).get('ranked_opportunities',0),
        'positive_clv':clv.get('summary',{}).get('positive',0),'negative_clv':clv.get('summary',{}).get('negative',0)},
      'command_center':{'top_opportunities':rows[:15],'highest_ev':opp.get('highest_ev',[])[:15],'arbitrage':opp.get('arbitrage',[])[:15],'middles':opp.get('middles',[])[:15],'steam_alerts':move.get('top_steam_alerts',[])[:15],'largest_moves':move.get('largest_moves',[])[:15],'best_line_shopping':shop.get('top_price_advantages',[])[:15],'top_rankings':rank.get('top_opportunities',[])[:15]},
      'distribution':{'recommendations':dict(recs),'best_books':dict(books),'markets':dict(markets)},
      'alerts':alerts[:50],
      'historical_kpis':{'history_records_for_date':len(history),'history_total_records':len(read_jsonl(HIST))},
      'source_health':health,
      'navigation':[{'id':'overview','label':'Overview'},{'id':'opportunities','label':'Opportunities'},{'id':'arbitrage','label':'Arbitrage'},{'id':'movement','label':'Market Movement'},{'id':'line-shopping','label':'Line Shopping'},{'id':'clv','label':'CLV'}]}
    for p in OUTS:p.parent.mkdir(parents=True,exist_ok=True);json.dump(report,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Professional dashboard:',build(a.date)['executive_summary'])
if __name__=='__main__':main()
