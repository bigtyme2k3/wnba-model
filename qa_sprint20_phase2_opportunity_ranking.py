"""QA for Sprint 20 Phase 2 opportunity ranking."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import wnba_opportunity_ranker as ranker


def run():
    assert round(ranker.weighted_score({'expected_value':1,'probability_edge':1,'confidence':1,'clv':1,'line_shopping':1,'market_depth':1}),2)==100
    assert ranker.tier(85,0.10,True)=='A'
    assert ranker.tier(72,0.05,True)=='B'
    assert ranker.tier(60,0.02,True)=='C'
    assert ranker.tier(90,-0.01,True)=='PASS'
    with TemporaryDirectory() as tmp:
        root=Path(tmp);shop=root/'shop.json';edges=root/'edges.jsonl';hist=root/'history.jsonl';warehouse=root/'warehouse.json';dashboard=root/'dashboard.json'
        shop.write_text(json.dumps({'markets':[{'date':'2026-07-27','player':'Test Player','game':'A @ B','market':'PTS','side':'OVER','best_book':'FanDuel','best_line':18.5,'best_odds':110,'book_count':3,'price_advantage':0.04,'market_disagreement_score':0.2}]}))
        edges.write_text(json.dumps({'edge_key':'e1','date':'2026-07-27','player':'Test Player','game':'A @ B','market':'PTS','selection':'OVER','model_projection':21,'model_probability':0.64,'implied_probability':0.4762,'probability_edge':0.1638,'expected_value':0.344,'confidence':0.82,'clv':0.5,'clv_grade':'POSITIVE','eligible_for_bet':True})+'\n')
        old=(ranker.SHOP,ranker.EDGES,ranker.HISTORY,ranker.OUTS)
        ranker.SHOP,ranker.EDGES,ranker.HISTORY,ranker.OUTS=shop,edges,hist,[warehouse,dashboard]
        first=ranker.build('2026-07-27');second=ranker.build('2026-07-27')
        ranker.SHOP,ranker.EDGES,ranker.HISTORY,ranker.OUTS=old
        assert first['summary']['ranked_opportunities']==1
        assert first['top_opportunities'][0]['tier']=='A'
        assert first['summary']['inserted_history_records']==1
        assert second['summary']['inserted_history_records']==0
        assert warehouse.exists() and dashboard.exists() and hist.exists()
    print('Sprint 20 Phase 2 opportunity ranking QA passed.')

if __name__=='__main__':run()
