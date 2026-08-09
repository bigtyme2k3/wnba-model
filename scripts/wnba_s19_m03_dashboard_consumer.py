from __future__ import annotations

import argparse, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
M02=DASH/'wnba_s19_m02_predictions.json'
RESULTS=DASH/'wnba_results_grading.json'
OUT=DASH/'wnba_s19_m03_dashboard_consumer.json'
AUDIT=DASH/'wnba_s19_m03_dashboard_consumer_audit.json'


def load(path, default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default


def build(target:str):
    m02=load(M02,{})
    if m02.get('status')!='READY' or str(m02.get('target_date') or '')[:10]!=target:
        raise SystemExit(f'M02 not READY/current for {target}: {m02.get("status")} {m02.get("target_date")}')

    # Results are generated from the existing deterministic grader. Waiting-for-actuals is valid.
    subprocess.run(['python','wnba_results_grader.py','--date',target],check=True)
    results=load(RESULTS,{})
    if str(results.get('target_date') or '')[:10]!=target:
        raise SystemExit(f'Results target mismatch: {results.get("target_date")} != {target}')

    games=m02.get('games') or []
    props=m02.get('player_props') or []
    best=m02.get('best_bets') or []
    portfolio=m02.get('portfolio') or []

    if not games: raise SystemExit('M03 refuses dashboard with zero canonical games')
    if not props: raise SystemExit('M03 refuses dashboard with zero canonical player prop predictions')
    if any(str(r.get('target_date') or target)[:10]!=target for r in props):
        raise SystemExit('M03 found off-date Player Props')
    if any(not r.get('model_projection') for r in props):
        raise SystemExit('M03 found Player Props without model projection')
    if any(str(r.get('injury_status') or '').upper() in {'OUT','DOUBTFUL'} and r.get('eligible') for r in props):
        raise SystemExit('M03 found actionable unavailable player')

    payload={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'target_date':target,
      'schema_version':'sprint19-m03-canonical-dashboard-consumer-v1',
      'status':'READY',
      'source_policy':{
        'games':'wnba_s19_m02_predictions.json.games',
        'player_props':'wnba_s19_m02_predictions.json.player_props',
        'best_bets':'wnba_s19_m02_predictions.json.best_bets',
        'portfolio':'wnba_s19_m02_predictions.json.portfolio',
        'results':'wnba_results_grading.json from deterministic grader',
        'legacy_phase2_fallback':False,
      },
      'games':games,'player_props':props,'best_bets':best,'portfolio':portfolio,'results':results,
      'summary':{
        'games':len(games),'player_props':len(props),'best_bets':len(best),'portfolio':len(portfolio),
        'results_status':results.get('status'),'results_archived_predictions':results.get('archived_predictions',0),
        'results_graded':(results.get('summary') or {}).get('graded_this_run',0),
      }
    }
    OUT.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    audit={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'READY','module':'SPRINT19-M03',
      'm02_status':m02.get('status'),'results_status':results.get('status'),'games':len(games),'player_props':len(props),
      'best_bets':len(best),'portfolio':len(portfolio),'actionable_unavailable_props':0,
      'phase2_best_bets_fallback_enabled':False,'phase2_portfolio_fallback_enabled':False,
      'all_consumers_single_source':True
    }
    AUDIT.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print('SPRINT19_M03_CONSUMER_READY',json.dumps(audit))
    return payload


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);a=ap.parse_args();build(a.date)

if __name__=='__main__':main()
