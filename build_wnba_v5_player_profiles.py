"""Build V5 player tendency profiles from verified graded ALT outcomes only."""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE=Path('data/history/wnba_alt_streak_history.jsonl')
OUTS=[Path('data/warehouse/wnba_v5_player_profiles.json'),Path('data/dashboard/wnba_v5_player_profiles.json')]
FINAL={'WIN','LOSS','PUSH','VOID'}
MIN_MARKET=8
MIN_PLAYER=15


def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def norm(v:Any)->str:return ' '.join(str(v or '').strip().split())
def rows()->list[dict[str,Any]]:
    out=[]
    if ARCHIVE.exists():
        for line in ARCHIVE.open(encoding='utf-8'):
            try:
                r=json.loads(line)
                if isinstance(r,dict) and str(r.get('outcome') or '').upper() in FINAL:out.append(r)
            except Exception:pass
    return out

def summarize(items:list[dict[str,Any]])->dict[str,Any]:
    wins=sum(str(r.get('outcome')).upper()=='WIN' for r in items)
    losses=sum(str(r.get('outcome')).upper()=='LOSS' for r in items)
    pushes=sum(str(r.get('outcome')).upper()=='PUSH' for r in items)
    decisions=wins+losses
    pnl=sum(num(r.get('profit_loss')) or 0 for r in items)
    return {'sample':len(items),'decisions':decisions,'wins':wins,'losses':losses,'pushes':pushes,
            'hit_rate':round(wins/decisions,4) if decisions else None,'profit_units':round(pnl,4),
            'roi':round(pnl/decisions,4) if decisions else None,'reliable':decisions>=MIN_MARKET}

def split(items:list[dict[str,Any]],field:str)->list[dict[str,Any]]:
    g:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in items:g[norm(r.get(field)) or 'Unknown'].append(r)
    out=[]
    for k,v in g.items():out.append({'group':k,**summarize(v)})
    return sorted(out,key=lambda x:(x['reliable'],x['decisions'],x['roi'] if x['roi'] is not None else -999),reverse=True)

def main()->None:
    data=rows();by_player:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in data:by_player[norm(r.get('player')) or 'Unknown'].append(r)
    profiles=[]
    for player,items in by_player.items():
        overall=summarize(items)
        market=split(items,'stat');side=split(items,'side');action=split(items,'streak_action')
        score_groups=defaultdict(list)
        for r in items:
            s=num(r.get('streak_score'))
            band='Unknown' if s is None else ('75+' if s>=75 else '70-74.9' if s>=70 else '60-69.9' if s>=60 else 'Below 60')
            score_groups[band].append(r)
        score=[{'group':k,**summarize(v)} for k,v in score_groups.items()]
        reliable_markets=[x for x in market if x['reliable']]
        best=max(reliable_markets,key=lambda x:x['roi'] if x['roi'] is not None else -999,default=None)
        worst=min(reliable_markets,key=lambda x:x['roi'] if x['roi'] is not None else 999,default=None)
        profiles.append({'player':player,'overall':overall,'profile_ready':overall['decisions']>=MIN_PLAYER,
                         'best_reliable_market':best,'weakest_reliable_market':worst,
                         'by_market':market,'by_side':side,'by_action':action,'by_score_band':score,
                         'available_context':{'rest':False,'home_away':False,'minutes':False,'opponent_rank':any(r.get('opponent_rank') is not None for r in items)},
                         'notes':['Verified graded outcomes only.','Small samples are descriptive and not predictive.']})
    profiles.sort(key=lambda p:(p['profile_ready'],p['overall']['decisions']),reverse=True)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'ok','summary':{
        'verified_graded_records':len(data),'players':len(profiles),'profiles_ready':sum(p['profile_ready'] for p in profiles),
        'minimum_player_decisions':MIN_PLAYER,'minimum_market_decisions':MIN_MARKET},
        'profiles':profiles,'policy':{'verified_outcomes_only':True,'shrinkage_rule':'segments below minimum sample remain descriptive','causal_claims':False,'missing_context_not_inferred':True}}
    for p in OUTS:
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))

if __name__=='__main__':main()
