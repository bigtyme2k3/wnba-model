"""Persist enriched live WNBA market predictions for later grading.

Primary input is the coverage scanner. If that scanner is empty, the tracker falls back
to enriched processed forecasts for future events inside 96 hours. Captures preserve
research context and do not imply that a wager was placed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LIVE=Path('data/forecast/live_opportunity_scanner.json')
ENRICHED=Path('data/forecast/enriched_market_predictions.json')
PRED=Path('data/forecast/closing_line_predictions.json')
TIMELINE=Path('data/market/market_timeline.json')
OUT=Path('data/validation/live_prediction_tracker.json')
DASH=Path('data/dashboard/wnba_live_prediction_tracker_summary.json')
VISIBILITY_HOURS=96
ACTION_HOURS=48


def now_dt()->datetime:
    return datetime.now(timezone.utc)


def iso(value:datetime)->str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def parse(value:Any)->datetime|None:
    if not value:return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError,ValueError):
        return None


def load(path:Path)->dict[str,Any]:
    if not path.exists():return {}
    raw=json.loads(path.read_text(encoding='utf-8'))
    return raw if isinstance(raw,dict) else {}


def prediction_rows()->list[dict[str,Any]]:
    enriched=load(ENRICHED).get('predictions',[])
    if isinstance(enriched,list) and enriched:return enriched
    payload=load(PRED)
    rows=payload.get('predictions',[]) or payload.get('forecasts',[])
    return rows if isinstance(rows,list) else []


def latest_observation_map()->dict[str,dict[str,Any]]:
    rows=load(TIMELINE).get('markets',[])
    output={}
    for row in rows if isinstance(rows,list) else []:
        obs=row.get('observations') or []
        if obs:output[str(row.get('market_id'))]=obs[-1]
    return output


def classify(commence:datetime,current:datetime)->str:
    hours=(commence-current).total_seconds()/3600
    return 'ACTIONABLE' if hours<=ACTION_HOURS else 'EARLY_MARKET'


def processed_fallback(rows:list[dict[str,Any]],current:datetime)->list[dict[str,Any]]:
    end=current+timedelta(hours=VISIBILITY_HOURS)
    candidates=[]
    for p in rows:
        commence=parse(p.get('commence_time_utc'))
        if not commence or not (current < commence <= end):continue
        row=dict(p);status=classify(commence,current)
        recommendation=row.get('scanner_recommendation') or ('WATCH' if status=='EARLY_MARKET' else 'PASS')
        if status=='EARLY_MARKET' and recommendation=='BET_NOW':recommendation='WATCH'
        row.update({
            'market_status':status,'actionable':status=='ACTIONABLE','validation_capture':True,
            'hours_to_tip':round((commence-current).total_seconds()/3600,3),
            'last_update_utc':p.get('current_time_utc') or p.get('snapshot_time_utc') or p.get('market_last_update_utc') or p.get('bookmaker_last_update_utc'),
            'scanner_recommendation':recommendation,
            'coverage_source':'ENRICHED_FORECAST_FALLBACK' if ENRICHED.exists() else 'PROCESSED_FORECAST_FALLBACK',
        })
        candidates.append(row)
    return candidates


def run()->dict[str,Any]:
    current=now_dt();captured=iso(current);live_payload=load(LIVE)
    markets=live_payload.get('markets',[]);markets=markets if isinstance(markets,list) else []
    predictions=prediction_rows();source='COVERAGE_SCANNER'
    if not markets:
        markets=processed_fallback(predictions,current)
        source=(markets[0].get('coverage_source') if markets else 'NO_FUTURE_MARKETS')

    pred_map={str(x.get('market_id')):x for x in predictions if isinstance(x,dict) and x.get('market_id')}
    obs_map=latest_observation_map();prior=load(OUT);records=prior.get('records',[]);records=records if isinstance(records,list) else []
    seen={(str(x.get('market_id')),str(x.get('snapshot_time_utc'))) for x in records if isinstance(x,dict)}
    added=[]
    for row in markets:
        mid=str(row.get('market_id') or '');p=pred_map.get(mid,{});latest=obs_map.get(mid,{})
        snapshot=(row.get('last_update_utc') or row.get('current_time_utc') or row.get('snapshot_time_utc') or latest.get('snapshot_time_utc') or captured)
        if not mid or (mid,str(snapshot)) in seen:continue
        status=row.get('market_status') or 'EARLY_MARKET'
        rec={
            'capture_id':f'{snapshot}|{mid}','captured_at_utc':captured,'market_id':mid,'event_id':row.get('event_id'),
            'commence_time_utc':row.get('commence_time_utc'),'home_team':row.get('home_team'),'away_team':row.get('away_team'),
            'bookmaker':row.get('bookmaker'),'market':row.get('market'),'participant':row.get('participant'),'selection':row.get('selection'),
            'market_status':status,'actionable':bool(row.get('actionable')),'validation_capture':bool(row.get('validation_capture',True)),
            'coverage_source':row.get('coverage_source') or source,'hours_to_tip':row.get('hours_to_tip'),
            'opening_line':row.get('opening_line'),'current_line':row.get('current_point'),'current_price':row.get('current_price'),'snapshot_time_utc':snapshot,
            'projected_closing_line':row.get('projected_closing_point') or p.get('projected_closing_point'),
            'projected_closing_price':row.get('projected_closing_price') or p.get('projected_closing_price'),
            'prediction_interval':row.get('projected_point_interval') or p.get('projected_point_interval'),
            'forecast_status':row.get('forecast_status') or p.get('forecast_status'),'forecast_confidence':row.get('forecast_confidence') or p.get('forecast_confidence'),
            'scanner_recommendation':row.get('scanner_recommendation') or ('WATCH' if status=='EARLY_MARKET' else 'PASS'),
            'opportunity_score':row.get('live_opportunity_score') if row.get('live_opportunity_score') is not None else row.get('opportunity_score'),
            'tier':row.get('tier'),'entry_action':row.get('entry_action'),'signal':row.get('signal'),
            'volatility_score':row.get('volatility_score'),'freshness_score':row.get('freshness_score'),
            'clv_confidence':row.get('clv_confidence'),'sportsbook_edge_score':row.get('sportsbook_edge_score'),
            'market_quality_grade':row.get('market_quality_grade'),'expected_closing_value':row.get('expected_closing_value'),
            'enrichment_source':row.get('enrichment_source'),'matched_clv_trends':row.get('matched_clv_trends',0),
            'matched_validated_trends':row.get('matched_validated_trends',0),
            'actual_closing_line':None,'actual_closing_price':None,'final_home_score':None,'final_away_score':None,
            'grade':None,'profit_units':None,'validation_status':'OPEN',
            'tracking_note':'Model-state capture only; no executed wager is implied.'
        }
        records.append(rec);added.append(rec);seen.add((mid,str(snapshot)))
    records.sort(key=lambda x:(str(x.get('captured_at_utc')),str(x.get('market_id'))))
    OUT.parent.mkdir(parents=True,exist_ok=True);DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'generated_at_utc':captured,'methodology':'Append-only captures of enriched future market states for closing-line and outcome validation.','records':records},indent=2),encoding='utf-8')
    open_records=sum(x.get('validation_status')=='OPEN' for x in records)
    summary={
        'generated_at_utc':captured,'status':'READY' if added else ('STANDBY' if not markets else 'NO_CHANGE'),
        'capture_source':source,'live_markets_seen':len(markets),
        'early_markets_seen':sum(x.get('market_status')=='EARLY_MARKET' for x in markets),
        'actionable_markets_seen':sum(x.get('market_status')=='ACTIONABLE' for x in markets),
        'records_added':len(added),'records_total':len(records),'open_records':open_records,
        'events_captured':len({x.get('event_id') for x in added if x.get('event_id')}),
        'early_records_added':sum(x.get('market_status')=='EARLY_MARKET' for x in added),
        'actionable_records_added':sum(x.get('market_status')=='ACTIONABLE' for x in added),
        'enriched_records_added':sum(bool(x.get('enrichment_source')) for x in added),
        'scored_records_added':sum(x.get('opportunity_score') is not None for x in added),
        'recommendation_counts_added':{k:sum(x.get('scanner_recommendation')==k for x in added) for k in ['BET_NOW','WATCH','PASS']},
        'top_captures':sorted(added,key=lambda x:-float(x.get('opportunity_score') or 0))[:25],
        'warning':'Tracking records preserve model state for research validation and do not represent placed wagers.'
    }
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));return summary


if __name__=='__main__':run()
