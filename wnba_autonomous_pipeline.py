from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard');WARE=Path('data/warehouse')
OUTS=[DASH/'wnba_autonomous_pipeline.json',WARE/'wnba_autonomous_pipeline.json']

def run_step(name:str,command:list[str],required:bool=True)->dict[str,Any]:
    started=datetime.now(timezone.utc)
    try:
        proc=subprocess.run(command,text=True,capture_output=True,timeout=900)
        status='PASS' if proc.returncode==0 else 'FAIL'
        return {'name':name,'status':status,'required':required,'command':' '.join(command),'returncode':proc.returncode,'duration_seconds':round((datetime.now(timezone.utc)-started).total_seconds(),2),'stdout_tail':proc.stdout[-3000:],'stderr_tail':proc.stderr[-3000:]}
    except Exception as exc:
        return {'name':name,'status':'FAIL','required':required,'command':' '.join(command),'returncode':None,'duration_seconds':round((datetime.now(timezone.utc)-started).total_seconds(),2),'error':str(exc)}

def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def build(target_date:str|None=None,execute_models:bool=True)->dict[str,Any]:
    steps=[]
    steps.append(run_step('readiness',[sys.executable,'wnba_readiness_engine.py']))
    readiness=load(DASH/'wnba_pipeline_readiness.json',{})
    ready=readiness.get('status')=='READY'
    if ready and execute_models:
        commands=[
          ('daily_edge',[sys.executable,'wnba_daily_edge_engine.py']+(['--date',target_date] if target_date else []),True),
          ('adaptive_confidence',[sys.executable,'wnba_adaptive_confidence_engine.py'],True),
          ('ensemble',[sys.executable,'wnba_ensemble_intelligence_engine.py'],True),
          ('monte_carlo',[sys.executable,'wnba_monte_carlo_scenario_engine.py']+(['--date',target_date] if target_date else []),True),
        ]
        for name,cmd,required in commands:
            if not Path(cmd[1]).exists():
                steps.append({'name':name,'status':'SKIP','required':required,'reason':f'{cmd[1]} missing'})
                continue
            result=run_step(name,cmd,required);steps.append(result)
            if required and result['status']=='FAIL':break
    else:
        steps.append({'name':'live_models','status':'SKIP','required':False,'reason':readiness.get('reason','Pipeline not ready')})
    for name,cmd in [
      ('data_lineage',[sys.executable,'wnba_data_lineage.py']),
      ('final_qa',[sys.executable,'wnba_final_qa.py']),
      ('dashboard_status',[sys.executable,'patch_dashboard_v4_pipeline_status.py']),
    ]:
        if Path(cmd[1]).exists():steps.append(run_step(name,cmd,required=False))
        else:steps.append({'name':name,'status':'SKIP','required':False,'reason':f'{cmd[1]} missing'})
    required_failures=[s['name'] for s in steps if s.get('required') and s.get('status')=='FAIL']
    qa=load(DASH/'wnba_final_qa.json',{})
    status='READY' if ready and not required_failures and qa.get('green_light') else 'WAIT' if not ready and not required_failures else 'FAIL'
    report={'sprint':11,'phase':'autonomous-orchestration','generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target_date or readiness.get('target_date'),'status':status,'readiness':readiness,'required_failures':required_failures,'steps':steps,'qa_status':qa.get('status'),'green_light':bool(qa.get('green_light'))}
    for path in OUTS:path.parent.mkdir(parents=True,exist_ok=True);json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps({'status':status,'readiness':readiness.get('status'),'steps':[(s['name'],s['status']) for s in steps],'green_light':report['green_light']},indent=2));return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--date');p.add_argument('--readiness-only',action='store_true');a=p.parse_args();build(a.date,not a.readiness_only)
if __name__=='__main__':main()
