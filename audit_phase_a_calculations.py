"""Sprint 20.5 Phase A: audit odds, probabilities, EV, tiers, and dashboard scaling."""
from __future__ import annotations
import argparse,json,math,statistics
from datetime import date,datetime,timezone
from pathlib import Path

EDGE=Path('data/history/wnba_edge_database.jsonl')
OPP=Path('data/dashboard/opportunity_finder.json')
DASH=Path('data/dashboard/professional_dashboard.json')
OUT=Path('data/audit/phase_a_calculation_audit.json')
TRACE=Path('data/audit/ev_trace_report.json')

def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

def read_json(path,default):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def read_jsonl(path):
    out=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out

def implied(odds):
    o=num(odds)
    if o is None or o==0:return None
    return 100/(o+100) if o>0 else abs(o)/(abs(o)+100)

def decimal_odds(odds):
    o=num(odds)
    if o is None or o==0:return None
    return 1+o/100 if o>0 else 1+100/abs(o)

def ev(prob,odds):
    p=num(prob);d=decimal_odds(odds)
    if p is None or d is None:return None
    return p*d-1

def build(target):
    now=datetime.now(timezone.utc).isoformat();rows=[r for r in read_jsonl(EDGE) if str(r.get('date'))==target]
    traces=[];formula_errors=[];suspicious=[]
    for r in rows:
        odds=num(r.get('american_odds'));p=num(r.get('model_probability'));stored_i=num(r.get('implied_probability'));stored_ev=num(r.get('expected_value'))
        calc_i=implied(odds);calc_ev=ev(p,odds)
        i_delta=None if calc_i is None or stored_i is None else abs(calc_i-stored_i)
        ev_delta=None if calc_ev is None or stored_ev is None else abs(calc_ev-stored_ev)
        flags=[]
        if p is None or not 0<=p<=1:flags.append('INVALID_MODEL_PROBABILITY')
        if calc_i is None or not 0<calc_i<1:flags.append('INVALID_IMPLIED_PROBABILITY')
        if i_delta is not None and i_delta>1e-5:flags.append('IMPLIED_FORMULA_MISMATCH')
        if ev_delta is not None and ev_delta>1e-5:flags.append('EV_FORMULA_MISMATCH')
        if stored_ev is not None and stored_ev>.20:flags.append('EV_ABOVE_20_PERCENT')
        if p is not None and (p<.01 or p>.99):flags.append('EXTREME_MODEL_PROBABILITY')
        if r.get('eligible_for_bet') and stored_ev is not None and not (.02<=stored_ev<=.20):flags.append('ELIGIBLE_OUTSIDE_EV_GUARDRAIL')
        trace={'edge_key':r.get('edge_key'),'player':r.get('player'),'game':r.get('game'),'market':r.get('market'),'selection':r.get('selection'),'american_odds':odds,'decimal_odds':decimal_odds(odds),'stored_implied_probability':stored_i,'calculated_implied_probability':calc_i,'model_probability':p,'stored_expected_value':stored_ev,'calculated_expected_value':calc_ev,'expected_value_pct':None if stored_ev is None else round(stored_ev*100,4),'eligible_for_bet':bool(r.get('eligible_for_bet')),'recommendation':r.get('recommendation'),'flags':flags}
        traces.append(trace)
        if any(x.endswith('MISMATCH') for x in flags):formula_errors.append(trace)
        if flags:suspicious.append(trace)
    evs=[num(r.get('expected_value')) for r in rows if num(r.get('expected_value')) is not None]
    eligible=[num(r.get('expected_value')) for r in rows if r.get('eligible_for_bet') and num(r.get('expected_value')) is not None]
    opp=read_json(OPP,{});dash=read_json(DASH,{})
    opp_rows=[r for r in opp.get('all_opportunities',[]) if str(r.get('date'))==target]
    opp_evs=[num(r.get('expected_value')) for r in opp_rows if num(r.get('expected_value')) is not None]
    expected_dash=round(100*sum(opp_evs)/len(opp_evs),2) if opp_evs else None
    actual_dash=num(dash.get('executive_summary',{}).get('average_expected_value_pct'))
    summary={'target_records':len(rows),'formula_mismatches':len(formula_errors),'suspicious_records':len(suspicious),'extreme_probability_records':sum('EXTREME_MODEL_PROBABILITY' in r['flags'] for r in traces),'ev_above_20_pct_records':sum('EV_ABOVE_20_PERCENT' in r['flags'] for r in traces),'eligible_records':len(eligible),'all_records_average_ev_pct':round(100*sum(evs)/len(evs),2) if evs else None,'eligible_average_ev_pct':round(100*sum(eligible)/len(eligible),2) if eligible else None,'all_records_median_ev_pct':round(100*statistics.median(evs),2) if evs else None,'dashboard_average_ev_pct':actual_dash,'dashboard_recalculated_average_ev_pct':expected_dash,'dashboard_scaling_match':actual_dash==expected_dash,'status':'FAIL' if formula_errors else 'WARN' if suspicious else 'PASS'}
    diagnosis=[]
    if summary['formula_mismatches']==0:diagnosis.append('American odds, implied probability, and EV formulas are internally consistent.')
    if summary['ev_above_20_pct_records']:diagnosis.append('Inflated dashboard EV originates upstream from extreme model probabilities, not dashboard percent formatting.')
    if not eligible:diagnosis.append('No target-date records passed eligibility guardrails; headline EV across all positive records is not an actionable-bet KPI.')
    report={'generated_at_utc':now,'target_date':target,'phase':'Sprint 20.5 Phase A','summary':summary,'diagnosis':diagnosis,'formula_errors':formula_errors[:100],'suspicious_examples':suspicious[:100]}
    OUT.parent.mkdir(parents=True,exist_ok=True);json.dump(report,OUT.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    json.dump({'generated_at_utc':now,'target_date':target,'traces':traces},TRACE.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Phase A audit:',build(a.date)['summary'])
if __name__=='__main__':main()
