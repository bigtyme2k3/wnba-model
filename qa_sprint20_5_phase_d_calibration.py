"""QA for Sprint 20.5 Phase D."""
import json, tempfile
from pathlib import Path
import validate_phase_d_probability_calibration as mod

def main():
    pairs=[(.9,1),(.8,0),(.7,1),(.6,0)]*150
    raw=mod.metrics(pairs)
    assert raw['samples']==600
    assert raw['brier_score']>0
    for model in (mod.fit_temperature(pairs),mod.fit_shrink(pairs),mod.fit_platt(pairs),mod.fit_isotonic(pairs)):
        values=[mod.apply(model,p) for p,_ in pairs]
        assert all(0<v<1 for v in values)
    original=mod.HISTORY
    with tempfile.TemporaryDirectory() as td:
        history=Path(td)/'history.jsonl'
        rows=[]
        for i in range(1000):
            p=.95 if i%2==0 else .8
            y='WIN' if i%3==0 else 'LOSS'
            rows.append(json.dumps({'date':f'2026-{1+(i//28)%9:02d}-{1+i%28:02d}','simulation_probability':p,'outcome':y}))
        history.write_text('\n'.join(rows),encoding='utf-8')
        mod.HISTORY=history
        mod.REPORT=Path(td)/'report.json'; mod.MODEL=Path(td)/'model.json'; mod.CURVES=Path(td)/'curves.json'
        report=mod.build('2026-07-27')
        assert report['summary']['training_records']==700
        assert report['summary']['validation_records']==300
        assert report['summary']['deployment_gate'] in {'PASS','HOLD'}
        assert mod.MODEL.exists() and mod.CURVES.exists()
    mod.HISTORY=original
    print('Sprint 20.5 Phase D QA passed')
if __name__=='__main__': main()
