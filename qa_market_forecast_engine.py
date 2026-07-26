"""QA for Sprint 17 Commit 1 market forecast engine."""
from __future__ import annotations
import json
from pathlib import Path

FORECAST=Path('data/forecast/market_forecasts.json')
PERF=Path('data/forecast/market_forecast_performance.json')
SUMMARY=Path('data/dashboard/wnba_market_forecast_summary.json')

def load(path):
    if not path.exists(): raise AssertionError(f'missing output: {path}')
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    f=load(FORECAST); p=load(PERF); s=load(SUMMARY)
    rows=f.get('forecasts',[])
    assert isinstance(rows,list)
    assert s.get('status') in {'READY','STANDBY'}
    assert s.get('markets_scored')==len(rows)
    ids=[x.get('market_id') for x in rows]
    assert len(ids)==len(set(ids)), 'duplicate market forecasts'
    ready=0
    for x in rows:
        assert x.get('forecast_status') in {'MODEL_READY','INSUFFICIENT_HISTORY'}
        c=float(x.get('forecast_confidence') or 0)
        assert 0<=c<=100
        if x['forecast_status']=='MODEL_READY':
            ready+=1
            assert int(x.get('model_sample_size') or 0)>=12
        if x.get('projected_closing_point') is not None:
            assert x.get('current_point') is not None
        if x.get('projected_closing_price') is not None:
            assert x.get('current_price') is not None
    assert s.get('model_ready')==ready
    assert s.get('insufficient_history')==len(rows)-ready
    assert int(p.get('training_examples') or 0)>=0
    assert int(p.get('models') or 0)>=0
    for key in ('within_half_point_rate','within_one_point_rate'):
        v=p.get(key)
        if v is not None: assert 0<=float(v)<=1
    if p.get('point_mae') is not None: assert float(p['point_mae'])>=0
    result={'status':'PASS','markets':len(rows),'model_ready':ready,'models':p.get('models',0),'backtests':p.get('backtest_predictions',0),'point_mae':p.get('point_mae')}
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
