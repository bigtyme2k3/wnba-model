"""Sprint 21 Phase 3 leakage-safe engineered feature builder."""
from __future__ import annotations
import argparse, json, math
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HISTORY=Path('data/history/wnba_model_history.jsonl')
OUT=Path('data/audit/sprint21_phase3_engineered_history.jsonl')
MANIFEST=Path('data/audit/sprint21_phase3_feature_manifest.json')
LEAKAGE={'actual','outcome','result','status','profit','payout','settled','hit','won','loss','final_actual','actual_value'}


def number(v:Any)->Optional[float]:
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def read_jsonl(path:Path)->List[Dict[str,Any]]:
    if not path.exists(): return []
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict): out.append(row)
        except Exception: pass
    return out

def pregame_numeric(row:Dict[str,Any])->Dict[str,float]:
    out={}
    for k,v in row.items():
        if k.lower() in LEAKAGE or k.lower().startswith('actual'): continue
        x=number(v)
        if x is not None: out[k]=x
    return out

def engineer(rows:List[Dict[str,Any]])->tuple[List[Dict[str,Any]],Dict[str,Any]]:
    ordered=sorted(rows,key=lambda r:(str(r.get('date') or ''),str(r.get('history_key') or '')))
    player_hist=defaultdict(lambda:deque(maxlen=10)); market_hist=defaultdict(lambda:deque(maxlen=50))
    output=[]; created=set(); base_counts=defaultdict(int)
    for row in ordered:
        new=dict(row); nums=pregame_numeric(row)
        for k in nums: base_counts[k]+=1
        # Within-row, pregame-only transformations.
        for k,x in nums.items():
            if abs(x)>0:
                new[f'{k}__abs']=abs(x); created.add(f'{k}__abs')
                new[f'{k}__signed_log']=math.copysign(math.log1p(abs(x)),x); created.add(f'{k}__signed_log')
        pairs=[('clv','ev_pct'),('clv','edge_pct'),('ev_pct','edge_pct'),('line','closing_line'),('book_count','history_games')]
        for a,b in pairs:
            if a in nums and b in nums:
                new[f'{a}__x__{b}']=nums[a]*nums[b]; created.add(f'{a}__x__{b}')
                new[f'{a}__minus__{b}']=nums[a]-nums[b]; created.add(f'{a}__minus__{b}')
        if 'american_odds' in nums:
            o=nums['american_odds']; p=100/(o+100) if o>0 else (-o)/((-o)+100)
            new['market_implied_probability']=p; created.add('market_implied_probability')
            if 'simulation_probability' in nums:
                new['model_market_probability_gap']=nums['simulation_probability']-p; created.add('model_market_probability_gap')
        player=str(row.get('player') or '')
        mkt=str(row.get('stat') or row.get('market') or 'UNKNOWN').upper()
        # Lagged history uses only prior rows, never current outcome.
        ph=player_hist[player]; mh=market_hist[mkt]
        if ph:
            new['player_prior_win_rate_5']=sum(ph)/len(ph); created.add('player_prior_win_rate_5')
            new['player_prior_samples']=len(ph); created.add('player_prior_samples')
        if mh:
            new['market_prior_win_rate_50']=sum(mh)/len(mh); created.add('market_prior_win_rate_50')
            new['market_prior_samples']=len(mh); created.add('market_prior_samples')
        output.append(new)
        result=str(row.get('outcome') or row.get('result') or '').upper()
        if result in {'WIN','LOSS'}:
            y=1 if result=='WIN' else 0
            if player: ph.append(y)
            mh.append(y)
    manifest={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'history_records':len(rows),'engineered_records':len(output),'engineered_features':sorted(created),'engineered_feature_count':len(created),'leakage_policy':'Only current-row pregame fields and strictly lagged prior outcomes are used.'}
    return output,manifest

def build(target_date:str)->Dict[str,Any]:
    rows=read_jsonl(HISTORY); engineered,manifest=engineer(rows); manifest['target_date']=target_date
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text('\n'.join(json.dumps(r,allow_nan=False) for r in engineered)+'\n',encoding='utf-8')
    MANIFEST.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Sprint 21 Phase 3 features:',manifest)
    return manifest

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); build(args.date)
if __name__=='__main__': main()
