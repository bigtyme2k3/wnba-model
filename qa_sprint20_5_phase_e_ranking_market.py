from __future__ import annotations
import json,tempfile
from pathlib import Path
import validate_phase_e_ranking_market_calibration as m

def main():
    assert abs(m.auc([0.1,0.9],[0,1])-1.0)<1e-9
    assert abs(m.auc([0.9,0.1],[0,1])-0.0)<1e-9
    ds=m.deciles([i/100 for i in range(100)],[0]*50+[1]*50)
    assert len(ds)==10 and ds[-1]['win_rate']>=ds[0]['win_rate']
    p=m.platt(0.8,{'a':1.0,'b':0.0}); assert abs(p-0.8)<1e-6
    met=m.metrics([0.2,0.3,0.7,0.8],[0,0,1,1]); assert met['auc']==1.0
    print(json.dumps({'status':'PASS','tests':5}))
if __name__=='__main__':main()
