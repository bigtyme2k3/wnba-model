from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

FORECAST=Path('data/forecast/closing_line_predictions.json')
PERF=Path('data/forecast/closing_line_predictor_performance.json')
DASH=Path('data/dashboard/wnba_closing_line_predictor_summary.json')

def load(path):
    if not path.exists(): raise SystemExit(f'missing {path}')
    return json.loads(path.read_text(encoding='utf-8'))
def parse(value):
    return datetime.fromisoformat(str(value).replace('Z','+00:00'))
def main():
    f=load(FORECAST); p=load(PERF); s=load(DASH)
    rows=f.get('forecasts',[]); assert isinstance(rows,list)
    assert s['markets_scored']==len(rows)
    ready=[x for x in rows if x.get('forecast_status')=='MODEL_READY']
    assert s['model_ready']==len(ready)
    assert s['insufficient_history']==len(rows)-len(ready)
    for x in rows:
        snapshot=x.get('snapshot_time_utc')
        assert snapshot, f"Missing snapshot_time_utc: {x.get('market_id')}"
        assert x.get('current_time_utc')==snapshot
        commence=x.get('commence_time_utc')
        assert commence
        expected=(parse(commence)-parse(snapshot)).total_seconds()/60
        assert abs(float(x.get('minutes_to_tip'))-round(expected,2)) < 0.011
    for x in ready:
        price=x.get('projected_closing_price')
        if price is not None:
            assert isinstance(price,int) and price != 0
            assert abs(price) >= 100
        interval=x.get('projected_price_interval') or []
        for value in interval:
            if value is not None:
                assert isinstance(value,int) and value != 0 and abs(value)>=100
        point_interval=x.get('projected_point_interval') or []
        assert len(point_interval)==2
    assert s['walk_forward_predictions']==p.get('walk_forward_predictions')
    for key in ('within_half_point_rate','within_one_point_rate','directional_accuracy'):
        value=p.get(key)
        assert value is None or 0 <= value <= 1
    mae=p.get('point_mae'); assert mae is None or mae >= 0
    print(json.dumps({'status':'PASS','markets':len(rows),'model_ready':len(ready),'timestamped_forecasts':len(rows),'walk_forward_predictions':p.get('walk_forward_predictions',0),'point_mae':mae},indent=2))
if __name__=='__main__':main()
