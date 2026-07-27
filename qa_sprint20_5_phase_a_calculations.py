"""QA for Sprint 20.5 Phase A calculation audit."""
from __future__ import annotations
import json,tempfile
from pathlib import Path
import audit_phase_a_calculations as a

def main():
    assert round(a.implied(-110),6)==0.52381
    assert round(a.implied(150),6)==0.4
    assert round(a.decimal_odds(-110),6)==1.909091
    assert round(a.ev(.55,-110),6)==0.05
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);target='2099-01-01';old=(a.EDGE,a.OPP,a.DASH,a.OUT,a.TRACE)
        a.EDGE=root/'edge.jsonl';a.OPP=root/'opp.json';a.DASH=root/'dash.json';a.OUT=root/'audit.json';a.TRACE=root/'trace.json'
        row={'edge_key':'x','date':target,'player':'P','game':'A @ B','market':'PTS','selection':'OVER','american_odds':-110,'implied_probability':a.implied(-110),'model_probability':.55,'expected_value':a.ev(.55,-110),'eligible_for_bet':True,'recommendation':'BET'}
        a.EDGE.write_text(json.dumps(row)+'\n',encoding='utf-8')
        a.OPP.write_text(json.dumps({'all_opportunities':[{'date':target,'expected_value':row['expected_value']}]}),encoding='utf-8')
        a.DASH.write_text(json.dumps({'executive_summary':{'average_expected_value_pct':5.0}}),encoding='utf-8')
        report=a.build(target)
        assert report['summary']['formula_mismatches']==0
        assert report['summary']['dashboard_scaling_match']
        assert report['summary']['status']=='PASS'
        assert a.OUT.exists() and a.TRACE.exists()
        a.EDGE,a.OPP,a.DASH,a.OUT,a.TRACE=old
    print('Sprint 20.5 Phase A calculation audit QA passed.')
if __name__=='__main__':main()
