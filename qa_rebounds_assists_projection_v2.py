"""Acceptance tests for joint REB/AST/combo Projection Engine v2."""
from __future__ import annotations

import json
from pathlib import Path

import wnba_rebounds_assists_projection_v2 as engine


def sample_rows():
    rows=[]
    for i in range(12):
        rows.append({
            'player':'Player One','team':'Example','position':'G','minutes':34+(i%3-1),
            'game_date':f'2026-06-{30-i:02d}','game_id':str(i),
            'scoring':{'total_pts':20+(i%5)},
            'boxscore':{'reb':5+(i%3),'oreb':1,'dreb':4+(i%3),'ast':7+(i%4)},
        })
    return rows


def minute_row():
    return {'player':'Player One','team':'Example','opponent':'Other','projected_minutes':35,'minutes_p10':31,'minutes_p90':38,'confidence':88,'data_quality_status':'complete','injury_status':'ACTIVE'}


def test_joint_distributions():
    result=engine.projection('Player One',sample_rows(),minute_row(),{'projected_points':23.5},{})
    for stat in ('REB','AST','PRA','PR','PA','RA'):
        dist=result['projections'][stat]
        assert 0<=dist['p10']<=dist['p25']<=dist['p50']<=dist['p75']<=dist['p90']
    assert result['simulation_count']==10000
    assert result['projected_pra']>=result['projected_pr']
    assert result['projected_pra']>=result['projected_pa']
    assert result['projected_pra']>=result['projected_ra']


def test_combo_identity():
    result=engine.projection('Player One',sample_rows(),minute_row(),{'projected_points':23.5},{})
    sim=result['simulation_values']
    for i in range(100):
        assert sim['PRA'][i] >= sim['PR'][i]
        assert sim['PRA'][i] >= sim['PA'][i]
        assert sim['PRA'][i] >= sim['RA'][i]


def test_market_bounds():
    result=engine.projection('Player One',sample_rows(),minute_row(),{'projected_points':23.5},{})
    markets=engine.compare_markets(result,[{'player':'Player One','stat':'REB','line':5.5,'best_over_price':-110,'best_under_price':-110,'best_over_book':'A','best_under_book':'B'},{'player':'Player One','stat':'PRA','line':34.5,'best_over_price':-105,'best_under_price':-115,'best_over_book':'A','best_under_book':'B'}])
    assert len(markets)==4
    for row in markets:
        assert 0<=row['hit_probability']<=1
        assert row['recommended_units']<=1
        assert row['action'] in {'BET','LEAN','PASS'}


def main():
    tests=[('joint distributions ordered',test_joint_distributions),('combo identities preserved',test_combo_identity),('market outputs bounded',test_market_bounds)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[row for row in results if not row['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True)
    json.dump(report,open('data/dashboard/wnba_rebounds_assists_projection_v2_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)


if __name__=='__main__':main()
