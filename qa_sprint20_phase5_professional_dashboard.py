"""QA for Sprint 20 Phase 5 professional dashboard."""
from __future__ import annotations
import json,tempfile
from pathlib import Path
import wnba_professional_dashboard as d

def write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload),encoding='utf-8')

def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);target='2099-01-01';old=(d.SOURCES,d.HIST,d.OUTS)
        d.SOURCES={k:root/f'{k}.json' for k in ('opportunities','movement','shopping','rankings','clv')};d.HIST=root/'history.jsonl';d.OUTS=[root/'warehouse.json',root/'dashboard.json',root/'docs.json']
        row={'date':target,'player':'Test Player','game':'A @ B','market':'PTS','side':'OVER','best_book':'FanDuel','expected_value':.08,'opportunity_index':84,'recommendation':'STRONG BET','actionable':True}
        write(d.SOURCES['opportunities'],{'target_date':target,'all_opportunities':[row],'highest_ev':[row],'arbitrage':[{'player':'Test Player','market':'PTS','over_book':'FanDuel','over_odds':110,'under_book':'DraftKings','under_odds':110,'arb_edge_pct':9.09}],'middles':[{'player':'Test Player','market':'PTS','middle_width':2.0}],'market_inefficiencies':[row]})
        write(d.SOURCES['movement'],{'target_date':target,'summary':{'tracked_markets':10,'steam_alerts':1,'reverse_line_movements':1},'top_steam_alerts':[{'player':'Test Player','market':'PTS','side':'OVER','total_directional_line_move':1,'book_count':2,'steam_score':80}],'reverse_line_movements':[],'largest_moves':[]})
        write(d.SOURCES['shopping'],{'target_date':target,'summary':{'markets':20},'top_price_advantages':[]})
        write(d.SOURCES['rankings'],{'target_date':target,'summary':{'ranked_opportunities':1},'top_opportunities':[row]})
        write(d.SOURCES['clv'],{'target_date':target,'summary':{'positive':1,'negative':0}})
        d.HIST.write_text(json.dumps(row)+'\n',encoding='utf-8')
        report=d.build(target)
        s=report['executive_summary'];assert s['scanned_opportunities']==1 and s['strong_bets']==1 and s['arbitrage_opportunities']==1
        assert report['distribution']['best_books']['FanDuel']==1
        assert report['alerts'][0]['type']=='ARBITRAGE'
        assert all(p.exists() and p.stat().st_size>0 for p in d.OUTS)
        d.SOURCES,d.HIST,d.OUTS=old
    print('Sprint 20 Phase 5 professional dashboard QA passed.')
if __name__=='__main__':main()
