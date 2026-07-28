"""QA for Sprint 21 Phase 3 engineered model rebuild."""
from __future__ import annotations
import json,tempfile
from pathlib import Path
import engineer_sprint21_phase3_features as eng
import validate_sprint21_phase3_models as val


def run():
    tests=0
    rows=[]
    for i in range(520):
        win=(i%4 in {0,1})
        rows.append({'date':f'2026-06-{1+i%28:02d}','history_key':str(i),'outcome':'WIN' if win else 'LOSS','player':f'P{i%20}','market':'PTS','clv':1.2 if win else -1.0,'ev_pct':4.0 if win else 1.0,'edge_pct':3.0 if win else -1.0,'american_odds':-110,'line':15.5,'closing_line':15.0,'actual':99})
    engineered,manifest=eng.engineer(rows)
    assert manifest['engineered_feature_count']>5; tests+=1
    assert 'actual__abs' not in manifest['engineered_features']; tests+=1
    assert any('model_market_probability_gap' not in r for r in engineered); tests+=1

    # Same-date outcomes must not be visible to another record on that date.
    leakage_fixture=[
        {'date':'2026-06-01','history_key':'1','outcome':'WIN','player':'P1','market':'PTS','clv':1.0},
        {'date':'2026-06-01','history_key':'2','outcome':'LOSS','player':'P1','market':'PTS','clv':-1.0},
        {'date':'2026-06-02','history_key':'3','outcome':'WIN','player':'P1','market':'PTS','clv':1.0},
    ]
    leakage_rows,_=eng.engineer(leakage_fixture)
    assert 'player_prior_win_rate_5' not in leakage_rows[0]
    assert 'player_prior_win_rate_5' not in leakage_rows[1]
    assert leakage_rows[2]['player_prior_samples']==2
    assert leakage_rows[2]['player_prior_win_rate_5']==0.5
    tests+=1

    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); history=root/'history.jsonl'; mf=root/'manifest.json'; out=root/'out.json'; best=root/'best.json'; markets=root/'markets.json'
        history.write_text('\n'.join(json.dumps(r) for r in engineered)+'\n'); mf.write_text(json.dumps(manifest))
        old=(val.HISTORY,val.MANIFEST,val.OUT,val.BEST,val.MARKETS)
        val.HISTORY,val.MANIFEST,val.OUT,val.BEST,val.MARKETS=history,mf,out,best,markets
        try: report=val.build('2026-07-27')
        finally: val.HISTORY,val.MANIFEST,val.OUT,val.BEST,val.MARKETS=old
        assert report['summary']['models_tested']>=1; tests+=1
        assert report['summary']['deployment_gate'] in {'PASS','HOLD'}; tests+=1
        assert out.exists() and best.exists() and markets.exists(); tests+=1
    return {'status':'PASS','tests':tests}
if __name__=='__main__':print(json.dumps(run()))
