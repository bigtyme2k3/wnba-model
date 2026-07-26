from __future__ import annotations
import json
from pathlib import Path

OUT=Path('data/forecast/sportsbook_leader_intelligence.json')
DASH=Path('data/dashboard/wnba_sportsbook_leader_summary.json')
BOOKS={'draftkings','fanduel'}

def load(path):
    if not path.exists(): raise SystemExit(f'missing {path}')
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    out=load(OUT); dash=load(DASH)
    books=out.get('sportsbooks',[]); markets=out.get('markets',[])
    assert dash.get('status') in {'READY','STANDBY'}
    assert len(books)==dash.get('sportsbooks_ranked')
    assert len(markets)==dash.get('markets_ranked')
    assert {x.get('bookmaker') for x in books}.issubset(BOOKS)
    assert len({x.get('bookmaker') for x in books})==len(books)
    for x in books:
        assert 0<=float(x.get('first_move_rate',0))<=1
        assert 0<=float(x.get('positive_clv_rate',0))<=1
        assert 0<=float(x.get('efficiency_score',0))<=100
        if x.get('average_follow_lag_minutes') is not None: assert x['average_follow_lag_minutes']>=0
        if x.get('forecast_point_mae') is not None: assert x['forecast_point_mae']>=0
    for x in markets:
        assert x.get('market_leader') in BOOKS
        assert len(x.get('books',[]))==2
        for b in x['books']:
            assert b.get('bookmaker') in BOOKS
            assert 0<=float(b.get('first_move_rate',0))<=1
    if books:
        assert dash.get('overall_leader')==books[0]['bookmaker']
        assert dash.get('status')=='READY'
    print(json.dumps({'status':'PASS','comparison_pairs':dash.get('comparison_pairs',0),'sportsbooks':len(books),'markets':len(markets),'overall_leader':dash.get('overall_leader')},indent=2))
if __name__=='__main__': main()
