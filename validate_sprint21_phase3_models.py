"""Sprint 21 Phase 3 engineered model comparison with rolling validation."""
from __future__ import annotations
import argparse,json,math
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Sequence
import validate_sprint21_phase2_feature_sets as p2

HISTORY=Path('data/audit/sprint21_phase3_engineered_history.jsonl')
MANIFEST=Path('data/audit/sprint21_phase3_feature_manifest.json')
OUT=Path('data/audit/sprint21_phase3_model_comparison.json')
BEST=Path('data/audit/sprint21_phase3_best_model.json')
MARKETS=Path('data/audit/sprint21_phase3_market_models.json')


def load(path:Path,default:Any)->Any:
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def safe_engineered(rows:Sequence[Dict[str,Any]])->List[str]:
    manifest=load(MANIFEST,{})
    fields=manifest.get('engineered_features',[])
    available=set(p2.available_numeric(rows))
    safe,_=p2.safe_features([f for f in fields if f in available])
    return safe

def base_features(rows:Sequence[Dict[str,Any]])->List[str]:
    ranked=load(Path('data/audit/feature_rankings.json'),{})
    entries=ranked.get('features',ranked if isinstance(ranked,list) else [])
    names=[r.get('feature') for r in entries if isinstance(r,dict) and r.get('feature')]
    safe,_=p2.safe_features(names)
    available=set(p2.available_numeric(rows))
    return [f for f in safe if f in available][:6]

def evaluate_variant(rows:Sequence[Dict[str,Any]],features:Sequence[str],steps:int,rate:float,l2:float)->Dict[str,Any]:
    folds=[]; probs=[]; ys=[]
    for fold,(train,valid) in enumerate(p2.rolling_splits(rows),1):
        tx,ty,vx,vy,usable=p2.matrices(train,valid,features)
        if not usable or len(set(ty))<2 or len(set(vy))<2: continue
        w=p2.fit_logistic(tx,ty,steps=steps,rate=rate,l2=l2); pp=p2.predict(w,vx)
        probs.extend(pp); ys.extend(vy)
        folds.append({'fold':fold,'train_records':len(ty),'validation_records':len(vy),'auc':round(p2.auc(pp,vy) if p2.auc(pp,vy) is not None else .5,6),'brier':round(p2.brier(pp,vy) or 0,6),'log_loss':round(p2.log_loss(pp,vy) or 0,6),'ece':round(p2.ece(pp,vy) or 0,6),'decile_spread':round(p2.decile_spread(pp,vy) or 0,6)})
    auc=p2.auc(probs,ys); fold_aucs=[x['auc'] for x in folds]
    stability=1-min(1,(max(fold_aucs)-min(fold_aucs))/.20) if fold_aucs else 0
    return {'features':list(features),'feature_count':len(features),'fold_count':len(folds),'validation_records':len(ys),'auc':None if auc is None else round(auc,6),'brier':None if not ys else round(p2.brier(probs,ys) or 0,6),'log_loss':None if not ys else round(p2.log_loss(probs,ys) or 0,6),'ece':None if not ys else round(p2.ece(probs,ys) or 0,6),'decile_spread':None if not ys else round(p2.decile_spread(probs,ys) or 0,6),'stability_score':round(stability,6),'folds':folds,'hyperparameters':{'steps':steps,'rate':rate,'l2':l2}}

def build(target_date:str)->Dict[str,Any]:
    rows=[r for r in p2.read_jsonl(HISTORY) if p2.outcome(r) is not None]
    base=base_features(rows); eng=safe_engineered(rows)
    candidates={
      'baseline_regularized':(base,350,.08,.02),
      'engineered_compact':(list(dict.fromkeys(base+eng[:10])),450,.06,.04),
      'engineered_extended':(list(dict.fromkeys(base+eng[:24])),500,.05,.08),
      'engineered_strong_regularization':(list(dict.fromkeys(base+eng[:16])),500,.04,.15),
    }
    results=[]
    for name,(features,steps,rate,l2) in candidates.items():
        if features:
            result=evaluate_variant(rows,features,steps,rate,l2); result['model']=name; results.append(result)
    results.sort(key=lambda r:((r.get('auc') or 0),r.get('decile_spread') or -9,-(r.get('log_loss') or 9)),reverse=True)
    best=results[0] if results else {}
    gate=bool(best and (best.get('auc') or 0)>=.53 and (best.get('decile_spread') or 0)>=.08 and (best.get('stability_score') or 0)>=.50 and best.get('fold_count',0)>=3)
    market_results={}
    if best:
        for market in sorted({p2.market(r) for r in rows}):
            subset=[r for r in rows if p2.market(r)==market]
            if len(subset)>=400:
                market_results[market]=evaluate_variant(subset,best['features'],450,.05,.08)
    summary={'history_records':len(p2.read_jsonl(HISTORY)),'settled_records':len(rows),'models_tested':len(results),'best_model':best.get('model'),'best_auc':best.get('auc'),'best_decile_spread':best.get('decile_spread'),'best_stability':best.get('stability_score'),'deployment_gate':'PASS' if gate else 'HOLD','status':'PASS'}
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target_date,'summary':summary,'models':results,'deployment_policy':{'minimum_auc':.53,'minimum_decile_spread':.08,'minimum_stability':.50,'minimum_folds':3,'production_unchanged':True}}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    BEST.write_text(json.dumps({'selected_model':best,'deployment_gate':summary['deployment_gate'],'production_enabled':False},indent=2),encoding='utf-8')
    MARKETS.write_text(json.dumps({'markets':market_results},indent=2),encoding='utf-8')
    print('Sprint 21 Phase 3:',summary); return payload

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
