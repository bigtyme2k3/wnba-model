"""Sprint 20 Phase 4: surface actionable WNBA betting opportunities."""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path

RANKINGS=Path('data/warehouse/wnba_opportunity_rankings.json')
SHOP=Path('data/warehouse/market_intelligence.json')
MOVEMENT=Path('data/warehouse/market_movement.json')
CONSENSUS=Path('data/warehouse/wnba_sportsbook_consensus.json')
HISTORY=Path('data/history/opportunity_finder_history.jsonl')
OUTS=[Path('data/warehouse/opportunity_finder.json'),Path('data/dashboard/opportunity_finder.json')]
ALLOWED={'DraftKings','FanDuel','Fanatics'}
WEIGHTS={'ranking':.35,'ev':.25,'market':.15,'shopping':.10,'confidence':.10,'clv':.05}

def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def clamp(x,lo=0.0,hi=1.0):return max(lo,min(hi,x))
def key(row):return '|'.join(norm(x) for x in (row.get('date'),row.get('player'),row.get('game'),row.get('market') or row.get('stat'),row.get('side') or row.get('signal')))
def base_key(row):return '|'.join(norm(x) for x in (row.get('date'),row.get('player'),row.get('game'),row.get('market') or row.get('stat')))

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

def implied(odds):
    o=num(odds)
    if o is None or o==0:return None
    return abs(o)/(abs(o)+100) if o<0 else 100/(o+100)

def recommendation(score,ev,eligible):
    if not eligible or ev is None or ev<=0:return 'PASS'
    if score>=82 and ev>=.08:return 'STRONG BET'
    if score>=68 and ev>=.04:return 'BET'
    if score>=55:return 'LEAN'
    return 'PASS'

def market_component(move):
    if not move:return .50
    score=num(move.get('market_confidence_score'))
    aligned=move.get('model_market_classification') in {'MODEL_AHEAD_OF_MOVE','MODEL_AGREES_WITH_MARKET'}
    reverse=bool(move.get('reverse_line_movement'))
    value=(score or 50)/100
    if aligned:value+=.10
    if reverse:value-=.15
    return clamp(value)

def opportunity_score(rank,shop,move):
    ev=num(rank.get('expected_value'));conf=num(rank.get('confidence'));clv=num(rank.get('clv'))
    if conf is not None and conf>1:conf/=100
    parts={
        'ranking':clamp((num(rank.get('opportunity_score')) or 0)/100),
        'ev':0 if ev is None else clamp((ev+.02)/.20),
        'market':market_component(move),
        'shopping':clamp(((num(shop.get('price_advantage')) or 0)+.01)/.08),
        'confidence':0 if conf is None else clamp((conf-.50)/.40),
        'clv':.50 if clv is None else clamp((clv+.5)/2.0),
    }
    return round(100*sum(WEIGHTS[k]*v for k,v in parts.items()),2),{k:round(v*100,2) for k,v in parts.items()}

def scan_arbitrage(consensus,target):
    out=[]
    for m in consensus.get('markets',[]):
        po=num(m.get('best_over_price'));pu=num(m.get('best_under_price'))
        io,iu=implied(po),implied(pu)
        if io is None or iu is None:continue
        total=io+iu;edge=1-total
        if edge<=-.03:continue
        out.append({'date':target,'player':m.get('player'),'game':m.get('game'),'market':m.get('stat'),'over_book':m.get('best_over_book'),'over_odds':po,'under_book':m.get('best_under_book'),'under_odds':pu,'combined_implied_probability':round(total,5),'arb_edge':round(edge,5),'arb_edge_pct':round(edge*100,2),'type':'ARBITRAGE' if edge>0 else 'NEAR_ARBITRAGE'})
    return sorted(out,key=lambda r:r['arb_edge'],reverse=True)

def scan_middles(target):
    path=Path(f'data/raw/line_shopping_{target}.csv')
    if not path.exists():return []
    groups=defaultdict(list)
    try:
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                book=r.get('book_title') or r.get('book')
                if book not in ALLOWED:continue
                side=str(r.get('side') or '').upper();line=num(r.get('line'))
                if side not in {'OVER','UNDER'} or line is None:continue
                k='|'.join(norm(x) for x in (r.get('player'),r.get('game'),r.get('stat') or r.get('market_type')))
                groups[k].append({'side':side,'line':line,'odds':num(r.get('odds')),'book':book,'player':r.get('player'),'game':r.get('game'),'market':r.get('stat') or r.get('market_type')})
    except Exception:return []
    out=[]
    for rows in groups.values():
        overs=[r for r in rows if r['side']=='OVER'];unders=[r for r in rows if r['side']=='UNDER']
        if not overs or not unders:continue
        best_over=min(overs,key=lambda r:r['line']);best_under=max(unders,key=lambda r:r['line']);width=best_under['line']-best_over['line']
        if width<=0:continue
        out.append({'date':target,'player':best_over['player'],'game':best_over['game'],'market':best_over['market'],'over_line':best_over['line'],'over_odds':best_over['odds'],'over_book':best_over['book'],'under_line':best_under['line'],'under_odds':best_under['odds'],'under_book':best_under['book'],'middle_width':round(width,3)})
    return sorted(out,key=lambda r:r['middle_width'],reverse=True)

def build(target):
    now=datetime.now(timezone.utc).isoformat()
    rankings=read_json(RANKINGS,{'all_ranked':[]});shopping=read_json(SHOP,{'markets':[]});movement=read_json(MOVEMENT,{'markets':[]});consensus=read_json(CONSENSUS,{'markets':[]})
    shop_idx={key(r):r for r in shopping.get('markets',[])};move_idx={key(r):r for r in movement.get('markets',[])}
    opportunities=[]
    for rank in rankings.get('all_ranked',[]):
        if str(rank.get('date'))!=target:continue
        k=key(rank);shop=shop_idx.get(k,{});move=move_idx.get(k,{})
        ev=num(rank.get('expected_value'));eligible=bool(rank.get('eligible_for_bet'))
        score,components=opportunity_score(rank,shop,move);rec=recommendation(score,ev,eligible)
        ineff=[]
        if (num(shop.get('market_disagreement_score')) or 0)>=.5:ineff.append('MARKET_DISAGREEMENT')
        if (num(shop.get('price_advantage')) or 0)>=.025:ineff.append('PRICE_OUTLIER')
        if (num(shop.get('line_range')) or 0)>=1:ineff.append('LINE_OUTLIER')
        if move.get('model_market_classification')=='MODEL_AHEAD_OF_MOVE':ineff.append('MODEL_AHEAD_OF_MARKET')
        if move.get('steam_detected'):ineff.append('STEAM_CONFIRMED')
        row={'opportunity_key':k,'date':target,'generated_at_utc':now,'player':rank.get('player'),'game':rank.get('game'),'market':rank.get('market'),'side':rank.get('side'),'best_book':rank.get('best_book'),'best_line':rank.get('best_line'),'best_odds':rank.get('best_odds'),'expected_value':ev,'expected_value_pct':None if ev is None else round(ev*100,2),'model_probability':rank.get('model_probability'),'confidence':rank.get('confidence'),'clv':rank.get('clv'),'ranking_score':rank.get('opportunity_score'),'opportunity_index':score,'recommendation':rec,'actionable':rec in {'STRONG BET','BET'},'market_inefficiencies':ineff,'components':components,'market_movement':{'classification':move.get('model_market_classification'),'steam_detected':bool(move.get('steam_detected')),'reverse_line_movement':bool(move.get('reverse_line_movement')),'market_confidence_score':move.get('market_confidence_score'),'stability_score':move.get('stability_score')},'line_shopping':{'book_count':shop.get('book_count'),'price_advantage':shop.get('price_advantage'),'line_range':shop.get('line_range'),'market_disagreement_score':shop.get('market_disagreement_score')}}
        opportunities.append(row)
    opportunities.sort(key=lambda r:(r['actionable'],r['opportunity_index'],r.get('expected_value') or -999),reverse=True)
    for i,r in enumerate(opportunities,1):r['finder_rank']=i
    arbitrage=scan_arbitrage(consensus,target);middles=scan_middles(target)
    existing={r.get('opportunity_key'):r for r in read_jsonl(HISTORY) if r.get('opportunity_key')};inserted=updated=0
    material=lambda x:{k:v for k,v in x.items() if k not in {'generated_at_utc','finder_rank'}}
    for row in opportunities:
        prior=existing.get(row['opportunity_key'])
        if prior is None:existing[row['opportunity_key']]=row;inserted+=1
        elif material(prior)!=material(row):existing[row['opportunity_key']]=row;updated+=1
    write_jsonl(HISTORY,sorted(existing.values(),key=lambda r:(str(r.get('date')),str(r.get('opportunity_key')))))
    report={'generated_at_utc':now,'target_date':target,'methodology':{'weights':WEIGHTS,'recommendations':{'STRONG BET':'index >=82, EV >=8%, eligible','BET':'index >=68, EV >=4%, eligible','LEAN':'index >=55 and positive EV, eligible','PASS':'otherwise'},'arbitrage':'best over and under implied probabilities sum below 1.0','near_arbitrage':'combined implied probability no worse than 1.03','middle':'lowest available over line is below highest available under line'},'summary':{'scanned_opportunities':len(opportunities),'strong_bets':sum(r['recommendation']=='STRONG BET' for r in opportunities),'bets':sum(r['recommendation']=='BET' for r in opportunities),'leans':sum(r['recommendation']=='LEAN' for r in opportunities),'passes':sum(r['recommendation']=='PASS' for r in opportunities),'positive_ev':sum((r.get('expected_value') or 0)>0 for r in opportunities),'market_inefficiencies':sum(bool(r['market_inefficiencies']) for r in opportunities),'arbitrage_opportunities':sum(r['type']=='ARBITRAGE' for r in arbitrage),'near_arbitrage_opportunities':sum(r['type']=='NEAR_ARBITRAGE' for r in arbitrage),'middle_opportunities':len(middles),'inserted_history_records':inserted,'updated_history_records':updated},'top_opportunities':opportunities[:25],'strong_bets':[r for r in opportunities if r['recommendation']=='STRONG BET'][:50],'bets':[r for r in opportunities if r['recommendation']=='BET'][:50],'leans':[r for r in opportunities if r['recommendation']=='LEAN'][:50],'highest_ev':sorted(opportunities,key=lambda r:r.get('expected_value') or -999,reverse=True)[:25],'market_inefficiencies':[r for r in opportunities if r['market_inefficiencies']][:50],'arbitrage':arbitrage[:50],'middles':middles[:50],'all_opportunities':opportunities[:500]}
    for p in OUTS:p.parent.mkdir(parents=True,exist_ok=True);json.dump(report,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Opportunity finder:',build(a.date)['summary'])
if __name__=='__main__':main()
