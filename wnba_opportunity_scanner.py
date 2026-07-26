"""Sprint 17 Commit 4: combine market intelligence into a ranked opportunity scanner.

The scanner is conservative by design. It ranks research opportunities from stored
market state and does not claim that a wager should be placed or will be profitable.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRED=Path('data/forecast/closing_line_predictions.json')
ENTRY=Path('data/market/entry_window_recommendations.json')
SIGNALS=Path('data/market/movement_classifications.json')
MOVES=Path('data/market/line_movements.json')
TRENDS=Path('data/trends/automated_trends.json')
VALIDATED=Path('data/trends/outcome_validated_trends.json')
BOOKS=Path('data/forecast/sportsbook_leader_normalized.json')
OUT=Path('data/forecast/opportunity_scanner.json')
DASH=Path('data/dashboard/wnba_opportunity_scanner_summary.json')


def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def load(path,key):
    if not path.exists(): return []
    raw=json.loads(path.read_text(encoding='utf-8'))
    value=raw.get(key,[]) if isinstance(raw,dict) else []
    return value if isinstance(value,list) else []
def clamp(v,lo=0.0,hi=100.0): return round(max(lo,min(hi,float(v))),2)
def num(v,default=0.0):
    try:return float(v)
    except (TypeError,ValueError):return default

def trend_match(row, dims):
    mapping={
      'bookmaker':row.get('bookmaker'),'market':row.get('market'),
      'selection':row.get('selection'),'movement_direction':row.get('direction'),
      'signal':row.get('signal')}
    return all(str(mapping.get(k))==str(v) for k,v in dims.items() if k in mapping)

def action_score(action):
    return {'BET_NOW':100,'WAIT':65,'WATCH':50,'PASS':0}.get(str(action or 'PASS'),0)
def signal_score(signal):
    return {'STEAM':100,'SHARP':90,'LATE_MONEY':80,'BOOK_LEADER':65,'MARKET_CORRECTION':35,'POSSIBLE_INJURY':25,'NORMAL':40}.get(str(signal or 'NORMAL'),40)

def run():
    predictions=load(PRED,'predictions') or load(PRED,'forecasts')
    entries={x.get('market_id'):x for x in load(ENTRY,'recommendations')}
    signals={x.get('market_id'):x for x in load(SIGNALS,'classifications')}
    moves={x.get('market_id'):x for x in load(MOVES,'movements')}
    trends=load(TRENDS,'trends')
    validated=load(VALIDATED,'trends') or load(VALIDATED,'validated_trends')
    book_payload=json.loads(BOOKS.read_text(encoding='utf-8')) if BOOKS.exists() else {}
    book_rows=book_payload.get('sportsbooks',[]) if isinstance(book_payload,dict) else []
    book_scores={x.get('bookmaker'):num(x.get('normalized_efficiency_score')) for x in book_rows}
    opportunities=[]
    for p in predictions:
        mid=p.get('market_id'); e=entries.get(mid,{}); s=signals.get(mid,{}); m=moves.get(mid,{})
        status=p.get('forecast_status') or p.get('status')
        forecast_ready=status=='MODEL_READY'
        forecast_conf=num(p.get('forecast_confidence')) if forecast_ready else 0
        expected_move=abs(num(p.get('expected_point_move')))
        forecast_component=clamp(forecast_conf*.75+min(25,expected_move*12)) if forecast_ready else 0
        entry_action=e.get('action') or e.get('recommendation') or 'PASS'
        entry_component=action_score(entry_action)
        signal=s.get('classification') or p.get('signal') or 'NORMAL'
        signal_component=signal_score(signal)
        volatility=num(m.get('volatility_score') or p.get('volatility_score'))
        volatility_component=clamp(100-abs(volatility-55)*1.3)
        rowctx={'bookmaker':p.get('bookmaker'),'market':p.get('market'),'selection':p.get('selection'),'direction':m.get('direction'),'signal':signal}
        matched=[t for t in trends if trend_match(rowctx,t.get('dimensions') or {})]
        trend_component=max([num(t.get('trend_score')) for t in matched],default=0)
        valid=[t for t in validated if trend_match(rowctx,t.get('dimensions') or {}) and str(t.get('validation_status') or t.get('status'))=='VALIDATED']
        outcome_component=100 if valid else 0
        book_component=book_scores.get(p.get('bookmaker'),0)
        score=clamp(.28*forecast_component+.20*entry_component+.15*signal_component+.10*volatility_component+.12*trend_component+.10*outcome_component+.05*book_component)
        if not forecast_ready: score=min(score,49)
        if entry_action=='PASS': score=min(score,39)
        tier='ELITE' if score>=85 else 'STRONG' if score>=70 else 'WATCH' if score>=55 else 'LOW' if score>=40 else 'AVOID'
        recommendation='BET_NOW' if score>=80 and entry_action=='BET_NOW' and forecast_ready else ('WATCH' if score>=55 else 'PASS')
        reasons=[]
        if forecast_ready: reasons.append(f"Forecast ready with {forecast_conf:.1f} confidence")
        else: reasons.append('Insufficient closing-line forecast history')
        reasons.append(f'Entry-window action: {entry_action}')
        reasons.append(f'Market signal: {signal}')
        if matched: reasons.append(f'{len(matched)} CLV trend pattern(s) matched')
        if valid: reasons.append(f'{len(valid)} outcome-validated trend(s) matched')
        opportunities.append({
          'market_id':mid,'event_id':p.get('event_id'),'commence_time_utc':p.get('commence_time_utc'),
          'home_team':p.get('home_team'),'away_team':p.get('away_team'),'bookmaker':p.get('bookmaker'),
          'market':p.get('market'),'participant':p.get('participant'),'selection':p.get('selection'),
          'current_point':p.get('current_point'),'current_price':p.get('current_price'),
          'projected_closing_point':p.get('projected_closing_point'),'projected_closing_price':p.get('projected_closing_price'),
          'expected_point_move':p.get('expected_point_move'),'forecast_status':status,
          'entry_action':entry_action,'signal':signal,'volatility_score':volatility,
          'matched_clv_trends':len(matched),'matched_validated_trends':len(valid),
          'components':{'forecast':forecast_component,'entry_window':entry_component,'signal':signal_component,'volatility':volatility_component,'trend':trend_component,'outcome_validation':outcome_component,'sportsbook':book_component},
          'opportunity_score':score,'tier':tier,'scanner_recommendation':recommendation,'reasons':reasons,
          'warning':'Research ranking only; not a guarantee or instruction to wager.'})
    opportunities.sort(key=lambda x:(-x['opportunity_score'],x.get('commence_time_utc') or '',x.get('market_id') or ''))
    generated=now(); OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'generated_at_utc':generated,'methodology':'Weighted combination of forecast, entry timing, market signal, volatility, trend, outcome validation, and normalized sportsbook context.','opportunities':opportunities},indent=2),encoding='utf-8')
    counts={k:sum(x['tier']==k for x in opportunities) for k in ['ELITE','STRONG','WATCH','LOW','AVOID']}
    recs={k:sum(x['scanner_recommendation']==k for x in opportunities) for k in ['BET_NOW','WATCH','PASS']}
    summary={'generated_at_utc':generated,'status':'READY' if opportunities else 'STANDBY','markets_scanned':len(opportunities),'tier_counts':counts,'recommendation_counts':recs,'top_opportunities':opportunities[:25],'warning':'The scanner ranks research opportunities and does not guarantee profit or recommend stake size.'}
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return summary

if __name__=='__main__': run()
