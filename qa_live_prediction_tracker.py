"""QA for live prediction tracker with enriched early-market coverage."""
from __future__ import annotations
import json
from pathlib import Path

TRACKER=Path('data/validation/live_prediction_tracker.json')
SUMMARY=Path('data/dashboard/wnba_live_prediction_tracker_summary.json')


def load(path:Path):
    assert path.exists(),f'Missing {path}'
    return json.loads(path.read_text(encoding='utf-8'))


def main()->None:
    tracker=load(TRACKER);summary=load(SUMMARY);records=tracker.get('records',[])
    assert isinstance(records,list)
    keys=[(r.get('market_id'),r.get('snapshot_time_utc')) for r in records]
    assert len(keys)==len(set(keys)),'Duplicate market/snapshot captures'
    valid_states={'OPEN','CLOSED','CLOSING_CAPTURED','GRADED','UNSUPPORTED','UNRESOLVED','VOID'}
    valid_sources={'COVERAGE_SCANNER','PROCESSED_FORECAST_FALLBACK','ENRICHED_FORECAST_FALLBACK',None}
    for r in records:
        assert r.get('market_id') and r.get('captured_at_utc') and r.get('snapshot_time_utc')
        assert r.get('validation_status') in valid_states
        assert r.get('scanner_recommendation') in {'BET_NOW','WATCH','PASS',None}
        assert r.get('market_status') in {'EARLY_MARKET','ACTIONABLE',None}
        assert r.get('coverage_source') in valid_sources
        if r.get('market_status')=='EARLY_MARKET':
            assert r.get('actionable') is False
            assert r.get('scanner_recommendation')!='BET_NOW'
        if r.get('market_status')=='ACTIONABLE':assert r.get('actionable') is True
        score=r.get('opportunity_score')
        if score is not None:assert 0<=float(score)<=100
        confidence=r.get('forecast_confidence')
        if confidence is not None:assert 0<=float(confidence)<=100
        for key in ('clv_confidence','sportsbook_edge_score','volatility_score'):
            value=r.get(key)
            if value is not None:assert 0<=float(value)<=100
        if r.get('enrichment_source'):
            assert r.get('market_quality_grade') in {'A+','A','B','C','RESEARCH','AVOID'}
            assert isinstance(r.get('expected_closing_value'),dict)
    assert summary.get('records_total')==len(records)
    assert summary.get('open_records')==sum(r.get('validation_status')=='OPEN' for r in records)
    assert summary.get('status') in {'READY','STANDBY','NO_CHANGE'}
    assert summary.get('capture_source') in {'COVERAGE_SCANNER','PROCESSED_FORECAST_FALLBACK','ENRICHED_FORECAST_FALLBACK','NO_FUTURE_MARKETS'}
    added=int(summary.get('records_added') or 0);assert added<=len(records)
    assert int(summary.get('early_records_added') or 0)+int(summary.get('actionable_records_added') or 0)==added
    assert int(summary.get('enriched_records_added') or 0)<=added
    assert int(summary.get('scored_records_added') or 0)<=added
    print(json.dumps({'status':'PASS','capture_source':summary.get('capture_source'),'records':len(records),'records_added':added,'enriched_records_added':summary.get('enriched_records_added',0),'scored_records_added':summary.get('scored_records_added',0),'open_records':summary.get('open_records'),'events_captured':summary.get('events_captured')},indent=2))


if __name__=='__main__':main()
