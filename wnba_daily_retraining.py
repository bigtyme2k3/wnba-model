"""M24 safe daily retraining controller.

This module audits the learning artifacts created by M17-M23 and authorizes a
production refresh only when every required validation artifact is healthy.
"""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(path,default):
    try:return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else default
    except Exception:return default

def build(target):
    artifacts={
        'grading':load('data/dashboard/wnba_results_grading.json',{}),
        'clv':load('data/dashboard/wnba_clv_summary.json',{}),
        'learning':load('data/dashboard/wnba_self_learning.json',{}),
        'calibration':load('data/dashboard/wnba_model_calibration.json',{}),
        'feature_importance':load('data/dashboard/wnba_feature_importance.json',{}),
        'optimizer':load('data/dashboard/wnba_hyperparameter_optimizer.json',{}),
    }
    checks={
        'grading_available':artifacts['grading'].get('status') in {'ok','waiting_for_actuals'},
        'clv_available':artifacts['clv'].get('status')=='ok',
        'learning_safe':artifacts['learning'].get('status')=='ok' and artifacts['learning'].get('safety',{}).get('rollback_on_validation_drop') is True,
        'calibration_valid':artifacts['calibration'].get('status')=='ok',
        'features_valid':artifacts['feature_importance'].get('status')=='ok',
        'optimizer_safe':artifacts['optimizer'].get('status')=='ok' and artifacts['optimizer'].get('policy',{}).get('rollback_safe') is True,
    }
    passed=all(checks.values()); sample=max(artifacts['calibration'].get('summary',{}).get('samples',0),artifacts['feature_importance'].get('summary',{}).get('graded_samples',0))
    production_update=passed and sample>=60 and (artifacts['learning'].get('update_applied') or artifacts['optimizer'].get('summary',{}).get('promoted'))
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok' if passed else 'blocked','checks':checks,'summary':{'checks_passed':sum(checks.values()),'checks_total':len(checks),'historical_samples':sample,'production_update_applied':bool(production_update)},'decision':'PROMOTE' if production_update else 'HOLD','reason':'validated improvement available' if production_update else 'safe hold: no validated improvement or insufficient sample'}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_daily_retraining.json','data/dashboard/wnba_daily_retraining.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Daily retraining:',build(a.date)['summary'])
if __name__=='__main__':main()
