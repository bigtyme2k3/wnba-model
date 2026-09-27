from __future__ import annotations

import argparse, json, math, subprocess
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
M02=DASH/'wnba_s19_m02_predictions.json'
RESULTS=DASH/'wnba_results_grading.json'
OUT=DASH/'wnba_s19_m03_dashboard_consumer.json'
AUDIT=DASH/'wnba_s19_m03_dashboard_consumer_audit.json'
ALLOWED_BOOKS={'draftkings','fanduel','fanatics'}
MARKET=DASH/'wnba_player_props.json'
BUY=DASH/'wnba_v5_buy_signals.json'
MAX_MARKET_AGE_MINUTES=180


def load(path, default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default


def exact_key(row):
    try:
        line=float(row.get('line'))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(line):
        return None
    return (str(row.get('player') or '').strip().casefold(),
            str(row.get('game') or '').strip().casefold(),
            str(row.get('stat') or '').strip().upper(), round(line, 3))


def build_research_watchlist(props, target):
    market=load(MARKET,{})
    stamp=str(market.get('generated_at_utc') or '')
    state={'status':'MARKET_UNAVAILABLE','market_generated_at_utc':stamp,
           'source':'exact current-slate canonical sportsbook props',
           'policy':'WATCH research only; no V5 approval, calibrated EV, or betting recommendation'}
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()/60
    except (TypeError, ValueError):
        return [],state
    if str(market.get('target_date') or '')[:10]!=target or age < -5 or age > MAX_MARKET_AGE_MINUTES:
        state['status']='MARKET_STALE_OR_OFF_SLATE'
        return [],state
    current={}
    for row in market.get('rows') or []:
        if not isinstance(row,dict):continue
        key=exact_key(row)
        if key and key not in current:current[key]=row
    candidates=[]
    for row in props:
        if (str(row.get('final_action') or '').upper()!='WATCH'
                or row.get('candidate_eligible') is not True
                or row.get('injury_source_verified') is not True
                or row.get('projection_validated') is not True
                or str(row.get('injury_status') or '').upper() not in {'ACTIVE','PROBABLE'}):
            continue
        side=str(row.get('recommendation') or '').upper()
        if side not in {'OVER','UNDER'}:continue
        source=current.get(exact_key(row))
        if not source:continue
        book=source.get('best_over_book' if side=='OVER' else 'best_under_book')
        price=source.get('best_over_price' if side=='OVER' else 'best_under_price')
        try:
            odds=float(price)
            confidence=float(row.get('confidence'))
            edge=float(row.get('edge'))
        except (TypeError, ValueError):
            continue
        if (str(book or '').strip().lower().replace(' ','') not in ALLOWED_BOOKS
                or not all(math.isfinite(v) for v in (odds,confidence,edge))
                or odds == 0 or abs(odds)>10000 or confidence<55 or abs(edge)<1.5):
            continue
        # The exact side and price must exist in the current market's book rows.
        if not any(str(b.get('book') or '').strip().lower()==str(book).strip().lower()
                   and str(b.get('side') or '').upper()==side
                   and str(b.get('price'))==str(int(odds))
                   for b in source.get('books') or [] if isinstance(b,dict)):
            continue
        candidates.append({
            'target_date':target,'player':row.get('player'),'game':row.get('game'),
            'stat':row.get('stat'),'side':side,'line':row.get('line'),
            'model_projection':row.get('model_projection'),'edge':edge,
            'confidence':confidence,'injury_status':row.get('injury_status'),
            'projected_minutes':row.get('projected_minutes'),
            'sportsbook':book,'american_odds':int(odds),'book_count':source.get('book_count'),
            'commence_time':source.get('commence_time'),
            'market_generated_at_utc':stamp,'final_action':'WATCH','research_only':True,
            'reason_not_bet':'No approved current V5 buy signal for this market',
        })
    candidates.sort(key=lambda r:(r['confidence'],abs(r['edge'])),reverse=True)
    selected=[];players=set();game_counts={}
    for row in candidates:
        player=str(row['player'] or '').casefold()
        game=str(row['game'] or '').casefold()
        if player in players or game_counts.get(game,0)>=2:continue
        selected.append(row);players.add(player);game_counts[game]=game_counts.get(game,0)+1
        if len(selected)>=6:break
    state.update({'status':'CURRENT','candidate_rows':len(candidates),'display_rows':len(selected),
                  'maximum_age_minutes':MAX_MARKET_AGE_MINUTES})
    return selected,state


def build(target:str):
    m02=load(M02,{})
    if m02.get('status')!='READY' or str(m02.get('target_date') or '')[:10]!=target:
        raise SystemExit(f'M02 not READY/current for {target}: {m02.get("status")} {m02.get("target_date")}')

    subprocess.run(['python','wnba_results_grader.py','--date',target],check=True)
    results=load(RESULTS,{})
    if str(results.get('target_date') or '')[:10]!=target:
        raise SystemExit(f'Results target mismatch: {results.get("target_date")} != {target}')

    games=m02.get('games') or []
    props=m02.get('player_props') or []
    best=m02.get('best_bets') or []
    portfolio=m02.get('portfolio') or []
    watchlist,watchlist_state=build_research_watchlist(props,target)
    buy=load(BUY,{})

    if not games: raise SystemExit('M03 refuses dashboard with zero canonical games')
    if not props: raise SystemExit('M03 refuses dashboard with zero canonical player prop predictions')
    if any(str(r.get('target_date') or target)[:10]!=target for r in props): raise SystemExit('M03 found off-date Player Props')
    # A valid projection may be exactly 0.0; reject only absent/null projections.
    if any(r.get('model_projection') is None for r in props): raise SystemExit('M03 found Player Props without model projection')
    if any(str(r.get('injury_status') or '').upper() in {'OUT','DOUBTFUL'} and r.get('eligible') for r in props): raise SystemExit('M03 found actionable unavailable player')
    if any(str(r.get('final_action') or r.get('action') or '').upper()!='BET' for r in best): raise SystemExit('M03 Best Bets contains a non-BET row')
    if any(r.get('research_only') is True for r in best): raise SystemExit('M03 Best Bets contains research-only rows')
    if any(str(r.get('sportsbook') or '').strip().lower().replace(' ','') not in ALLOWED_BOOKS for r in best): raise SystemExit('M03 Best Bets contains an unsupported sportsbook')

    payload={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,
      'schema_version':'sprint19-m03-canonical-dashboard-consumer-v1','status':'READY',
      'source_policy':{'games':'wnba_s19_m02_predictions.json.games','player_props':'wnba_s19_m02_predictions.json.player_props','best_bets':'wnba_s19_m02_predictions.json.best_bets','portfolio':'wnba_s19_m02_predictions.json.portfolio','results':'wnba_results_grading.json from deterministic grader','legacy_phase2_fallback':False,'research_watchlist':'M02 WATCH rows plus exact same-slate canonical sportsbook lines; never approved as Best Bets'},
      'games':games,'player_props':props,'best_bets':best,'portfolio':portfolio,'results':results,
      'research_watchlist':watchlist,'research_watchlist_state':watchlist_state,
      'buy_signal_source_date':str(buy.get('injury_target_date') or '')[:10],
      'summary':{'games':len(games),'player_props':len(props),'best_bets':len(best),'research_watchlist':len(watchlist),'portfolio':len(portfolio),'results_status':results.get('status'),'results_archived_predictions':results.get('archived_predictions',0),'results_graded':(results.get('summary') or {}).get('graded_this_run',0)}
    }
    OUT.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'READY','module':'SPRINT19-M03','m02_status':m02.get('status'),'results_status':results.get('status'),'games':len(games),'player_props':len(props),'best_bets':len(best),'research_watchlist_rows':len(watchlist),'research_watchlist_market_status':watchlist_state['status'],'portfolio':len(portfolio),'actionable_unavailable_props':0,'phase2_best_bets_fallback_enabled':False,'phase2_portfolio_fallback_enabled':False,'all_consumers_single_source':True}
    AUDIT.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print('SPRINT19_M03_CONSUMER_READY',json.dumps(audit))

    # M04 freezes M03 into the single downstream dashboard decision contract.
    subprocess.run(['python','scripts/wnba_s19_m04_decision_contract.py','--date',target],check=True)
    print('SPRINT19_M04_WIRED', json.dumps({'target_date':target,'single_dashboard_contract':True}))
    return payload


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);a=ap.parse_args();build(a.date)

if __name__=='__main__':main()
