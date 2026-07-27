from __future__ import annotations
import json,tempfile
from pathlib import Path
import wnba_market_movement_engine as m

def run():
    assert m.directional_move(20.5,21.5,'OVER')==1.0
    assert m.directional_move(20.5,19.5,'UNDER')==1.0
    assert m.classify_model(1.0,{'side':'OVER','rank':5})=='MODEL_AHEAD_OF_MOVE'
    assert m.classify_model(-1.0,{'side':'OVER','rank':5})=='MODEL_DISAGREES_WITH_MARKET'
    old=(m.SNAPS,m.RANKINGS,m.HISTORY,m.OUTS)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);m.SNAPS=root/'snaps.jsonl';m.RANKINGS=root/'rank.json';m.HISTORY=root/'hist.jsonl';m.OUTS=[root/'warehouse.json',root/'dashboard.json']
        snaps=[
          {'date':'2026-07-27','captured_at_utc':'2026-07-27T12:00:00+00:00','stage':'open','player':'Test Player','game':'A vs B','stat':'PTS','signal':'OVER','line':20.5,'over_price':-110,'book':'DraftKings'},
          {'date':'2026-07-27','captured_at_utc':'2026-07-27T12:30:00+00:00','stage':'snapshot','player':'Test Player','game':'A vs B','stat':'PTS','signal':'OVER','line':21.5,'over_price':-115,'book':'FanDuel'},
          {'date':'2026-07-27','captured_at_utc':'2026-07-27T13:00:00+00:00','stage':'close','player':'Test Player','game':'A vs B','stat':'PTS','signal':'OVER','line':22.0,'over_price':-120,'book':'Fanatics'}]
        m.SNAPS.write_text(''.join(json.dumps(x)+'\n' for x in snaps));m.RANKINGS.write_text(json.dumps({'all_ranked':[{'date':'2026-07-27','player':'Test Player','game':'A vs B','market':'PTS','side':'OVER','rank':1}]}))
        first=m.build('2026-07-27');second=m.build('2026-07-27')
        assert first['summary']['tracked_markets']==1
        assert first['summary']['steam_alerts']==1
        assert first['summary']['inserted_history_records']==1
        assert second['summary']['inserted_history_records']==0
        assert second['summary']['updated_history_records']==0
        row=first['markets'][0]
        assert row['timeline'][0]['stage']=='open' and row['timeline'][-1]['stage']=='close'
        assert row['total_directional_line_move']==1.5
        assert row['model_market_classification']=='MODEL_AHEAD_OF_MOVE'
        assert all(p.exists() for p in m.OUTS)
    m.SNAPS,m.RANKINGS,m.HISTORY,m.OUTS=old
    print('Sprint 20 Phase 3 market movement QA passed.')
if __name__=='__main__':run()
