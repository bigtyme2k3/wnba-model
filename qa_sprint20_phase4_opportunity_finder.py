"""QA for Sprint 20 Phase 4 opportunity finder."""
from __future__ import annotations
import json,tempfile
from pathlib import Path
import wnba_opportunity_finder as f


def write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload),encoding='utf-8')


def main():
    assert round(f.implied(-110),5)==0.52381
    assert round(f.implied(120),5)==0.45455
    assert f.recommendation(85,.10,True)=='STRONG BET'
    assert f.recommendation(70,.05,True)=='BET'
    assert f.recommendation(58,.02,True)=='LEAN'
    assert f.recommendation(90,.10,False)=='PASS'
    arb=f.scan_arbitrage({'markets':[{'player':'A','game':'G','stat':'PTS','best_over_price':110,'best_over_book':'FanDuel','best_under_price':110,'best_under_book':'DraftKings'}]},'2099-01-01')
    assert arb and arb[0]['type']=='ARBITRAGE' and arb[0]['arb_edge']>0
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);target='2099-01-01'
        old=(f.RANKINGS,f.SHOP,f.MOVEMENT,f.CONSENSUS,f.HISTORY,f.OUTS)
        f.RANKINGS=root/'rank.json';f.SHOP=root/'shop.json';f.MOVEMENT=root/'move.json';f.CONSENSUS=root/'cons.json';f.HISTORY=root/'history.jsonl';f.OUTS=[root/'warehouse.json',root/'dashboard.json']
        # Deliberately strong inputs should clear the weighted index >=82 threshold.
        rank={'date':target,'player':'Test Player','game':'A @ B','market':'PTS','side':'OVER','best_book':'FanDuel','best_line':20.5,'best_odds':105,'expected_value':.15,'model_probability':.65,'confidence':.90,'clv':1.5,'opportunity_score':95,'eligible_for_bet':True}
        write(f.RANKINGS,{'all_ranked':[rank]})
        write(f.SHOP,{'markets':[{'date':target,'player':'Test Player','game':'A @ B','market':'PTS','side':'OVER','book_count':3,'price_advantage':.07,'line_range':1.5,'market_disagreement_score':.75}]})
        write(f.MOVEMENT,{'markets':[{'date':target,'player':'Test Player','game':'A @ B','market':'PTS','side':'OVER','model_market_classification':'MODEL_AHEAD_OF_MOVE','steam_detected':True,'reverse_line_movement':False,'market_confidence_score':100,'stability_score':80}]})
        write(f.CONSENSUS,{'markets':[{'player':'Test Player','game':'A @ B','stat':'PTS','best_over_price':110,'best_over_book':'FanDuel','best_under_price':110,'best_under_book':'DraftKings'}]})
        first=f.build(target);second=f.build(target)
        assert first['summary']['scanned_opportunities']==1
        assert first['summary']['strong_bets']==1
        assert first['summary']['arbitrage_opportunities']==1
        assert first['summary']['market_inefficiencies']==1
        assert second['summary']['inserted_history_records']==0
        assert second['summary']['updated_history_records']==0
        row=first['top_opportunities'][0]
        assert row['opportunity_index']>=82,row['opportunity_index']
        assert row['recommendation']=='STRONG BET'
        assert {'PRICE_OUTLIER','LINE_OUTLIER','MODEL_AHEAD_OF_MARKET','STEAM_CONFIRMED'}<=set(row['market_inefficiencies'])
        assert all(p.exists() and p.stat().st_size>0 for p in f.OUTS)
        f.RANKINGS,f.SHOP,f.MOVEMENT,f.CONSENSUS,f.HISTORY,f.OUTS=old
    print('Sprint 20 Phase 4 opportunity finder QA passed.')

if __name__=='__main__':main()
