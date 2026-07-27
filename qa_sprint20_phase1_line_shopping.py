"""QA for Sprint 20 Phase 1 line shopping."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
import wnba_line_shopping_engine as engine

def main():
    assert round(engine.implied(-110),6)==round(110/210,6)
    assert round(engine.implied(150),6)==0.4
    assert engine.better_price(-105,-110)==-105
    with tempfile.TemporaryDirectory() as tmp:
        old=os.getcwd();os.chdir(tmp)
        try:
            Path('data/warehouse').mkdir(parents=True)
            payload={'summary':{},'markets':[{'player':'Player A','game':'A@B','stat':'PTS','book_count':3,'books':['DraftKings','FanDuel','Fanatics'],'consensus_line':19.5,'line_range':1.0,'best_over_price':-105,'best_over_book':'Fanatics','best_under_price':100,'best_under_book':'DraftKings','consensus_over_probability':0.52,'consensus_under_probability':0.48}]}
            Path(engine.CONSENSUS).write_text(json.dumps(payload),encoding='utf-8')
            first=engine.build('2026-07-27')
            assert first['summary']['markets']==2
            assert first['summary']['inserted_history_records']==2
            over=next(r for r in first['markets'] if r['side']=='OVER')
            assert over['best_book']=='Fanatics' and over['best_odds']==-105
            second=engine.build('2026-07-27')
            assert second['summary']['inserted_history_records']==0
            assert second['summary']['updated_history_records']==0
            assert len(Path(engine.HISTORY).read_text().splitlines())==2
            assert Path('data/warehouse/market_intelligence.json').is_file()
            assert Path('data/dashboard/market_intelligence.json').is_file()
        finally:os.chdir(old)
    print('Sprint 20 Phase 1 line shopping QA passed.')
if __name__=='__main__':main()
