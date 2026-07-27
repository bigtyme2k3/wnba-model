"""Sprint 20.5 Phase B: audit probability provenance and field selection."""
from __future__ import annotations
import argparse,json,math
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path

MODEL=Path('data/history/wnba_model_history.jsonl')
EDGE=Path('data/history/wnba_edge_database.jsonl')
OUT=Path('data/audit/phase_b_data_flow_audit.json')
TRACE=Path('data/audit/probability_source_trace.json')
PRIORITY=('simulation_probability','model_probability','probability','confidence','final_score','consensus_score')

def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

def prob(v):
    n=num(v)
    if n is None:return None
    if n>1:n/=100
    return max(0.0,min(1.0,n))

def rows(path):
    out=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict):out.append(r)
            except Exception:pass
    return out

def key(r):return str(r.get('history_key') or r.get('edge_key') or r.get('source_history_key') or '|'.join(str(r.get(x) or '') for x in ('date','player','game','stat','line','signal')))

def selected(r):
    for f in PRIORITY:
        p=prob(r.get(f))
        if p is not None:return f,p
    return None,None

def build(target):
    source=[r for r in rows(MODEL) if str(r.get('date'))==target]
    edges={key(r):r for r in rows(EDGE) if str(r.get('date'))==target}
    counts=Counter();availability=Counter();confusion=Counter();traces=[]
    for r in source:
        for f in PRIORITY:
            if prob(r.get(f)) is not None:availability[f]+=1
        field,p=selected(r);counts[field or 'NONE']+=1
        edge=edges.get(key(r),{})
        stored=prob(edge.get('model_probability'))
        candidates={f:prob(r.get(f)) for f in PRIORITY if prob(r.get(f)) is not None}
        same_as=[]
        if stored is not None:
            same_as=[f for f,v in candidates.items() if abs(v-stored)<=1e-6]
        if field in {'confidence','final_score','consensus_score'}:confusion['score_field_selected_as_probability']+=1
        if p is not None and p>=.95:confusion['selected_probability_gte_95pct']+=1
        if len(same_as)>1:confusion['ambiguous_equal_fields']+=1
        if stored is not None and p is not None and abs(stored-p)>1e-6:confusion['edge_source_mismatch']+=1
        traces.append({'key':key(r),'player':r.get('player'),'market':r.get('stat') or r.get('market'),'selected_field':field,'selected_probability':p,'edge_model_probability':stored,'matching_source_fields':same_as,'available_probability_candidates':candidates,'flags':[x for x,b in [('SCORE_FIELD_USED_AS_PROBABILITY',field in {'confidence','final_score','consensus_score'}),('EXTREME_PROBABILITY',p is not None and p>=.95),('SOURCE_EDGE_MISMATCH',stored is not None and p is not None and abs(stored-p)>1e-6)] if b]})
    suspicious=sum(bool(t['flags']) for t in traces)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'WARN' if suspicious else 'PASS','summary':{'source_records':len(source),'matched_edge_records':sum(key(r) in edges for r in source),'unmatched_edge_records':sum(key(r) not in edges for r in source),'suspicious_records':suspicious,'selected_field_counts':dict(counts),'field_availability':dict(availability),'findings':dict(confusion)},'selection_priority':list(PRIORITY),'data_flow':['data/history/wnba_model_history.jsonl','wnba_edge_database.py:model_probability_for','data/history/wnba_edge_database.jsonl','wnba_opportunity_finder.py','wnba_professional_dashboard.py'],'diagnosis':'The first non-null field in selection_priority becomes model_probability. Score-like fields are unsafe fallbacks unless explicitly calibrated as probabilities.','top_traces':sorted(traces,key=lambda x:(len(x['flags']),x.get('selected_probability') or 0),reverse=True)[:100]}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8');TRACE.write_text(json.dumps({'generated_at_utc':report['generated_at_utc'],'target_date':target,'records':traces},indent=2,allow_nan=False),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Phase B audit:',build(a.date)['summary'])
if __name__=='__main__':main()
